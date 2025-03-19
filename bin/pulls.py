#!/usr/bin/env python3
import argparse
from dataclasses import dataclass
import json
import os
import projects
from typing import Dict

class PullException(Exception):
    pass
@dataclass
class Issue:
    number: int
    projectname: str

def getPullProjects(allProjects:projects.Projects):
    rc:projects.ProjectList = []
    for project in allProjects.projects:
        if project.localChanges > 0:
            raise PullException("Project " + project.name + " has local changes")
        if project.gitChanges > 0:
            rc.append( project)
    if len(rc) == 0:
        raise PullException("No changes in Github")
    return rc
initialText = "Please update me"
def buildPulltext(allProjects:projects.Projects, pullProjects:projects.ProjectList, issue:Issue)->projects.PullTexts:
    if pullProjects == None or len(pullProjects)== 0:
        raise PullException("No projects to pull")
    pullText:projects.PullTexts = projects.PullTexts() # Default generic pull text update me!!
    pullText.text = initialText
    pullText.topic = initialText
    if allProjects.pulltext != None: # Currently not used. Pass topic and text
        pullText = allProjects.pulltext
        if allProjects.pulltext.topic != "" and allProjects.pulltext != "":
            pullText.draft = False
    if issue != None:
        projects.eprint("Get pulltext from issue " + issue.number + " in " + issue.projectname)
        if issue.projectname == pullProjects[len(pullProjects)-1]:
            # The last project is the project which is used to generate the changes.md file.
            # The issue number can be passed to the pull request creation
            return None 
        else:
            # Read topic and text from github issue
            js = projects.ghapi("GET", "/repos/" + allProjects.owner + "/" + issue.projectname 
            + "/issues/" + str(issue.number))
            result =json.loads(js)
            pullText.topic = result['title']
            pullText.text = result['body']
            pullText.draft = False
    else:
        bugs = ""
        features = ""
        topic = ""
        onePrText = ""
        type = ""
        for project in allProjects.projects:
            if project.pulltexts:
                for pt in project.pulltexts:
                    if pt.type == 'bug':
                        bugs += "* " + project.name + ":" + pt.topic + "<br>\n" 
                        if pt.text != None and pt.text != "":
                            bugs += "    " + pt.text + "<br>\n"
                    else:
                        features += "* " + project.name + ":" + pt.topic + "<br>\n" 
                        if pt.text != None and pt.text != "":
                            features += "    " + pt.text + "<br>\n"
                    # if there is only one topic, use it, otherwise use default update me text
                    if topic == "":
                        topic = pt.topic
                        onePrText = pt.text
                        type = pt.type
                    else:
                        topic = None
        if bugs != "":
            pullText.text = "##Bugs:\n" + bugs 
        if features != "":
            pullText.text  += "##Features:\n" + features 
        if topic != None and topic != "":
            pullText.topic = topic
            pullText.text = onePrText
            pullText.draft = False
            pullText.type = type
    return pullText


def sync(projectsList:projects.Projects):
    projects.doWithProjects(projectsList,'sync')
        
def createPullRequests( projectsList:projects.Projects, issue:Issue):
    try:
        # compareProjects(projects)
        projects.doWithProjects(projectsList,'sync', projectsList)
        projects.doWithProjects(projectsList,'push', projectsList)
        projects.doWithProjects(projectsList,'compare', projectsList)
        pullProjects = getPullProjects(projectsList)
        projects.doWithProjects(projectsList,'readpulltext')
        projects.doWithProjects(projectsList,'dependencies', projectsList,"remote",None)
        pulltext = buildPulltext(projectsList, pullProjects, issue)
        projects.doWithProjects(projectsList,'createpull', projectsList, pullProjects, pulltext, issue )
        projects.doWithProjects(projectsList,'updatepulltext', projectsList, pullProjects , pulltext)
    except Exception as err:
        for arg in err.args:
            if type(arg) is str:
                projects.eprint("Creating aborted " + arg)
        exit(2)
def initProjects(branch):
    for project in projectsList.projects:   
        # fork will fail if project it is already forked.The error will be ignored
        owner = projectsList.login
        if not projects.isProjectForked(project.name ):
            owner = projectsList.owner    
        if not os.path.exists( project.name ):
            projects.executeCommand(['git','clone', 'git@github.com:' + 
            owner + '/' +project.name + '.git' ])
    projects.doWithProjects(projectsList,'newbranch', branch)

def dependencies( projectList, type:str, *args):
    mainproject = projectList['mainproject']
    owner = projectList['owner']
    pwd = os.getcwd()
    try:
        pkgjson = json.load(os.path.join(mainproject, 'package.json'))
        projects.doWithProjects('dependencies', projectList['projects'])
    finally:
        os.chdir(pwd)


parser = argparse.ArgumentParser()
subparsers = parser.add_subparsers(help="sub-commands")

parser.add_argument("-p", "--projects", help="projects.json file ",  nargs='?', default='projects.json', const='projects.json')

parser_init = subparsers.add_parser("init", help="init: forks and clones repositories")
parser_init.add_argument("-b", "--branch", help="New branch name",  nargs='?', default='main')
parser_init.set_defaults(command='init')

parser_switch = subparsers.add_parser("branch", help="branch: Switches to the given branch")
parser_switch.add_argument("branch", help="branch name")
parser_switch.set_defaults(command='branch')

parser_syncpull = subparsers.add_parser("syncpull", help="sync: pull request from root root repositories")
parser_syncpull.set_defaults(command='syncpull')
parser_syncpull.add_argument("pullrequest", help="Pull request <project name>:<number> in project  e.g 'angular:14'" , type= str)
parser_syncpull.add_argument("branch", help="New branch for the Pull request " , type= str)

parser_sync = subparsers.add_parser("sync", help="sync: pulls main and current branch from root repositories")
parser_sync.set_defaults(command='sync')

parser_test = subparsers.add_parser("test", help="test: execute npm test for all projects")
parser_test.set_defaults(command='test')
parser_release = subparsers.add_parser("release", help="releases all projects")
parser_release.set_defaults(command='release')
parser_create = subparsers.add_parser("createpull", help="createpull: creates pull requests ")
parser_create.add_argument("-i", "--issue", help="Issue number ",type = int,  nargs='?', default=None)
parser_create.set_defaults(command='createpull')

parser_dependencies = subparsers.add_parser("dependencies", help="dependencies changes dependencies in package.json files ]")
parser_dependencies.add_argument("dependencytype", help="command ", choices=['local','pull','remote'], default='local')
parser_dependencies.add_argument("-r", "--pullrequest", help="Pull request <project name>:<number> in project  e.g 'angular:14'" ,type = str,  nargs='?', default=None)
parser_dependencies.set_defaults(command='dependencies')

args = parser.parse_args()
projectsList = projects.readprojects(args.projects)

try:   
    match args.command:
        case "init":
            initProjects(args.branch)
        case "branch":
            projects.doWithProjects(projectsList,'newbranch', args.branch)
        case "sync":
            projects.doWithProjects(projectsList,'sync',projectsList)
        case "syncpull":
            pr  = projects.getPullrequestFromString(args.pullrequest)
            prs = projects.getRequiredPullrequests(projects.Project(pr['name']), projectsList.owner, pr['name'] + ":" + str(pr['number']))
            projects.doWithProjects(projectsList,'syncpull',projectsList, prs, args.branch)
        case "test":
                    projects.doWithProjects(projectsList,'test')
        case "createpull":
            ii = None
            if args.issue != None:
                i = args.issue.split(':')
                ii= Issue(i(0), int(i(1)))
            createPullRequests( projectsList, ii)
        case "dependencies":
            if args.dependencytype == 'pull':
                pr  = projects.getPullrequestFromString(args.pullrequest)
                for project in projectsList.projects:
                    if project.name == pr["name"]:
                        project.pullrequestid = pr['number']
                        projects.doWithProjects(projectsList,'sync', projectsList)
                        projects.doWithProjects(projectsList,'dependencies', projectsList, args.dependencytype, project)
                        exit(0)
                project.eprint("pullrequest not found:" + args.pullrequest)
            else:
                projects.doWithProjects(projectsList,'sync',projectsList)
                projects.doWithProjects(projectsList,'dependencies', projectsList, args.dependencytype, None)

        case "release":
                projects.doWithProjects(projectsList,'prepareGitForRelease', projectsList )
                projects.doWithProjects(projectsList,'dependencies', projectsList, 'release')
except projects.SyncException as err1:
    projects.eprint(projects.currentProject + ": " + err1.args[0])
    for arg in err1.args:
        projects.eprint( arg)
    exit(2)
except Exception as err:
    for arg in err.args:
        projects.eprint( arg)
    exit(2)
