#!/usr/bin/env python3
import argparse
import sys
from collections.abc import MutableSequence
from dataclasses import dataclass
import json
import os
import repositories
from typing import Dict

class PullException(Exception):
    pass
@dataclass
class Issue:
    number: int
    repositoryname: str

def getPullRepositorys(allRepositorys:repositories.Repositorys)->MutableSequence[repositories.Repository]:
    rc:MutableSequence[repositories.Repository] = []
    for repository in allRepositorys.repositorys:
        if repositories.localChanges > 0:
            raise PullException("Repository " + repositories.name + " has local changes")
        if repositories.gitChanges > 0:
            rc.append( repository)
    if len(rc) == 0:
        raise PullException("No changes in Github")
    return rc
initialText = "Please update me"
def buildPulltext(allRepositorys:repositories.Repositorys, pullRepositorys, issue:Issue)->repositories.PullTexts:
    if pullRepositorys == None or len(pullRepositorys)== 0:
        raise PullException("No repositorys to pull")
    pullText:repositories.PullTexts = repositories.PullTexts() # Default generic pull text update me!!
    pullText.text = initialText
    pullText.topic = initialText
    if allRepositorys.pulltext != None: # Currently not used. Pass topic and text
        pullText = allRepositorys.pulltext
        if allRepositorys.pulltext.topic != "" and allRepositorys.pulltext != "":
            pullText.draft = False
    if issue != None:
        repositories.eprint("Get pulltext from issue " + issue.number + " in " + issue.repositoryname)
        if issue.repositoryname == pullRepositorys[len(pullRepositorys)-1]:
            # The last repository is the repository which is used to generate the changes.md file.
            # The issue number can be passed to the pull request creation
            return None 
        else:
            # Read topic and text from github issue
            js = repositories.ghapi("GET", "/repos/" + allRepositorys.owner + "/" + issue.repositoryname 
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
        for repository in allRepositorys.repositorys:
            if repositories.pulltexts:
                for pt in repositories.pulltexts:
                    if pt.type == 'bug':
                        bugs += "* " + repositories.name + ":" + pt.topic + "<br>\n" 
                        if pt.text != None and pt.text != "":
                            bugs += "    " + pt.text + "<br>\n"
                    else:
                        features += "* " + repositories.name + ":" + pt.topic + "<br>\n" 
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


def sync(repositorysList:repositories.Repositorys):
    repositories.doWithRepositorys(repositorysList,'sync')
        
def createPullRequests( repositorysList:repositories.Repositorys, issue:Issue):
    try:
        # compareRepositorys(repositorys)
        repositories.doWithRepositorys(repositorysList,'sync', repositorysList)
        repositories.doWithRepositorys(repositorysList,'push', repositorysList)
        repositories.doWithRepositorys(repositorysList,'compare', repositorysList)
        pullRepositorys = getPullRepositorys(repositorysList)
        repositories.doWithRepositorys(repositorysList,'readpulltext')
        repositories.doWithRepositorys(repositorysList,'dependencies', repositorysList,"remote",None)
        pulltext = buildPulltext(repositorysList, pullRepositorys, issue)
        repositories.doWithRepositorys(repositorysList,'createpull', repositorysList, pullRepositorys, pulltext, issue )
        repositories.doWithRepositorys(repositorysList,'updatepulltext', repositorysList, pullRepositorys , pulltext)
    except Exception as err:
        for arg in err.args:
            if type(arg) is str:
                repositories.eprint("Creating aborted " + arg)
        exit(2)
def initRepositorys(branch):
    for repository in repositorysList.repositorys:   
        # fork will fail if repository it is already forked.The error will be ignored
        owner = repositorysList.login
        if not repositories.isRepositoryForked(repositories.name ):
            owner = repositorysList.owner    
        if not os.path.exists( repositories.name ):
            repositories.executeCommand(['git','clone', repositories.getGitPrefix(repositorysList)  + 
            owner + '/' + repositories.name + '.git' , '--origin', owner ])
            repositories.setUrl(repository)
    repositories.doWithRepositorys(repositorysList,'newbranch', branch)
    repositories.doWithRepositorys(repositorysList,'npminstall')


def dependencies( repositoryList, type:str, *args):
    mainrepository = repositoryList['mainrepository']
    owner = repositoryList['owner']
    pwd = os.getcwd()
    try:
        pkgjson = json.load(os.path.join(mainrepository, 'package.json'))
        repositories.doWithRepositorys('dependencies', repositoryList['repositorys'])
    finally:
        os.chdir(pwd)


parser = argparse.ArgumentParser()
subparsers = parser.add_subparsers(help="sub-commands")

parser.add_argument("-p", "--repositorys", help="repositories.json file ",  nargs='?', default='repositories.json', const='repositories.json')

parser_init = subparsers.add_parser("init", help="init: forks and clones repositories")
parser_init.add_argument("-b", "--branch", help="New branch name",  nargs='?', default='main')
parser_init.set_defaults(command='init')

parser_switch = subparsers.add_parser("branch", help="branch: Switches to the given branch")
parser_switch.add_argument("branch", help="branch name")
parser_switch.set_defaults(command='branch')

parser_syncpull = subparsers.add_parser("syncpull", help="sync: pull request from root root repositories")
parser_syncpull.set_defaults(command='syncpull')
parser_syncpull.add_argument("pullrequest", help="Pull request <repository name>:<number> in repository  e.g 'angular:14'" , type= str)
parser_syncpull.add_argument("branch", help="New branch for the Pull request " , type= str)

parser_sync = subparsers.add_parser("sync", help="sync: pulls main and current branch from root repositories")
parser_sync.set_defaults(command='sync')

parser_test = subparsers.add_parser("test", help="test: execute npm test for all repositorys")
parser_test.set_defaults(command='test')
parser_testorwait = subparsers.add_parser("testorwait", help="Executed via github event pull_request")
parser_testorwait.set_defaults(command='testorwait')
parser_testorwait.add_argument("pullrequest", help="Pull request <repository name>:<number> ", type = str)
parser_testorwait.add_argument("pullbody", help="Description of pull request ", type = str)

parser_release = subparsers.add_parser("release", help="releases all repositorys")
parser_release.set_defaults(command='release')
parser_create = subparsers.add_parser("createpull", help="createpull: creates pull requests ")
parser_create.add_argument("-i", "--issue", help="Issue number ",type = int,  nargs='?', default=None)
parser_create.set_defaults(command='createpull')

parser_dependencies = subparsers.add_parser("dependencies", help="dependencies changes dependencies in package.json files ]")
parser_dependencies.add_argument("dependencytype", help="command ", choices=['local','pull','remote'], default='local')
parser_dependencies.add_argument("-r", "--pullrequest", help="Pull request <repository name>:<number> in repository  e.g 'angular:14'" ,type = str,  nargs='?', default=None)
parser_dependencies.set_defaults(command='dependencies')

args = parser.parse_args()
repositorysList = repositories.readrepositorys(args.repositorys)

try:   
    match args.command:
        case "init":
            initRepositorys(args.branch)
        case "branch":
            repositories.doWithRepositorys(repositorysList,'newbranch', args.branch)
            repositories.doWithRepositorys(repositorysList,'npminstall')

        case "sync":
            repositories.doWithRepositorys(repositorysList,'sync',repositorysList)
        case "syncpull":
            pr  = repositories.getPullrequestFromString(args.pullrequest)
            prs = repositories.getRequiredPullrequests(repositories.Repository(pr['name']), repositorysList.owner, pr['name'] + ":" + str(pr['number']))
            repositories.doWithRepositorys(repositorysList,'syncpull',repositorysList, prs, args.branch)
            repositories.doWithRepositorys(repositorysList,'npminstall')
        case "test":
                    repositories.sendTestStatus(repositorysList, repositories.TestStatus.running,False)
                    repositories.doWithRepositorys(repositorysList,'test', repositorysList)
                    status = repositories.getTestResultStatus(repositorysList)
                    repositories.sendTestStatus(repositorysList, status)
                    if status != repositories.TestStatus.success:
                        exit(2)
        case "testorwait":
              pr  = repositories.getPullrequestFromString(args.pullrequest)
              requiredPrs = repositories.getRequiredReposFromPRDescription(args.pullbody,pr)
              for idx, p in enumerate(requiredPrs):
                  if p.name == pr.name and pr.number == p.number and idx == 0:
                      # args.pullrequest belongs to the first repository
                      repositories.testRepository( )

              repositories.eprint(pr)
        case "createpull":
            if repositorysList.owner == repositorysList.login:
                raise repositories.SyncException("Owner must be different from logged in user: " + repositorysList.owner + " == " + repositorysList.login )
            ii = None
            if args.issue != None:
                i = args.issue.split(':')
                ii= Issue(i(0), int(i(1)))
            createPullRequests( repositorysList, ii)
        case "dependencies":
            if args.dependencytype == 'pull':
                pr  = repositories.getPullrequestFromString(args.pullrequest)
                for repository in repositorysList.repositorys:
                    if repositories.name == pr["name"]:
                        repositories.pullrequestid = pr['number']
                        repositories.doWithRepositorys(repositorysList,'sync', repositorysList)
                        repositories.doWithRepositorys(repositorysList,'dependencies', repositorysList, args.dependencytype, repository)
                        exit(0)
                repositories.eprint("pullrequest not found:" + args.pullrequest)
            else:
                repositories.doWithRepositorys(repositorysList,'sync',repositorysList)
                repositories.doWithRepositorys(repositorysList,'dependencies', repositorysList, args.dependencytype, None)

        case "release":
                repositories.doWithRepositorys(repositorysList,'prepareGitForRelease', repositorysList )
                repositories.doWithRepositorys(repositorysList,'dependencies', repositorysList, 'release')
except repositories.SyncException as err1:
    repositories.eprint(repositories.currentRepository + ": " + err1.args[0])
    for arg in err1.args:
        repositories.eprint( arg)
    exit(2)
except Exception as err:
    for arg in err.args:
        repositories.eprint( arg)
    exit(2)
