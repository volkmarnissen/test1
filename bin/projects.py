#!/usr/bin/env python3
from dataclasses import dataclass
import functools
import json
import argparse
import os
import subprocess
import sys
import re
from typing import Any, Dict
import typing

owner = ""

@dataclass
class PullTexts:
    type: str= ""
    topic: str= ""
    text: str = ""
    draft: bool = True
    
@functools.total_ordering
class Project:      
    def __init__(self, name:str):
        self.name = name
        self.pulltexts =[]
        self.remoteBranch = None
    def _is_valid_operand(self, other):
        return (hasattr(other, "name") and
                hasattr(other, "owner"))

    def __eq__(self, other):
        if not self._is_valid_operand(other):
            return NotImplemented
        return self.name.lower() == other.name.lower

    def __lt__(self, other):
        if not self._is_valid_operand(other):
            return NotImplemented
        return self.name.lower() < other.name.lower
    owner: str
    name: str
    branch: str
    remoteBranch: str = None
    localChanges: int
    gitChanges: int
    pulltexts: list[PullTexts] = []
    pullrequestid: int = None

type ProjectList = list[Project]

class Projects: 
    def __init__(self, para:Dict):
        self.owner = para['owner']
        self.projects = para['projects']
    owner: str
    projects: ProjectList
    pulltext: PullTexts = None

class SyncException(Exception):
    pass

def eprint(*args, **kwargs):
    print(*args, file=sys.stderr, **kwargs)

def executeCommand(cmdArgs: list[str], *args, **kwargs)-> str:
    ignoreErrors = kwargs.get('ignoreErrors', None)
    eprint( ' '.join( cmdArgs))
    result = subprocess.Popen(cmdArgs,
	cwd=os.getcwd(),
 	stdout=subprocess.PIPE,
 	stderr=subprocess.PIPE) 
    out, err = result.communicate()
    err = err.decode("utf-8")
    return_code = result.returncode
    if err != b'' and err != '' and not ignoreErrors:
        eprint(err)
    if return_code != 0:
        if out != b'':
            eprint(out.decode("utf-8"))
        return "".encode('utf-8')
    else:
        if out.decode("utf-8") == '':
            return '{"status": "OK"}'.encode('utf-8')
    return out

def executeSyncCommand(cmdArgs: list[str], *args, **kwargs)-> str:
    result = subprocess.Popen(cmdArgs,
	cwd=os.getcwd(),
 	stdout=subprocess.PIPE,
 	stderr=subprocess.PIPE) 
    out, err = result.communicate()
    result.returncode
    if result.returncode != 0:
        raise SyncException( ' '.join(cmdArgs), out.decode("utf-8"))
    return out
   
def ghapi(method:str, url:str, *args)->str:

    return executeSyncCommand(['gh','api','-H', "Accept: application/vnd.github+json",
                           '-H',"X-GitHub-Api-Version: 2022-11-28",
                           '-X', method,
                           url ]+ list(*args))
def ghcompare( repo:str, owner:str, base:str, head:str, *args, **kwargs)->str:
    sha = kwargs.get('sha', None)
    delimiter = '...'
    if sha != None:
        delimiter = '..'
    url = '/repos/' + owner + '/' + repo + '/compare/' + base  + delimiter + head
    return ghapi( 'GET', url )
def json2Projects(dct:Any ):
    if 'name' in dct:
        return  Project( dct['name'])
    return dct
def readprojects(projectsFile)->Projects:
    try:
        input_file = open (projectsFile)
        jsonDict:Dict[str,Any] =  json.load(input_file, object_hook=json2Projects)
        return Projects(jsonDict)
    except Exception as e:
        print("something went wrong " , e)
# syncs main from original github source to local git branch (E.g. 'feature')
def syncProject(project: Project):
    project.branch =  subprocess.getoutput('git rev-parse --abbrev-ref HEAD')
    out = executeCommand(['git','remote','show','origin'])
    match = re.search(r'.*Push *URL:[^:]*:([^\/]*)', out.decode("utf-8"))
    project.owner = match.group(1)
    match = re.search(r'.*Remote[^:]*:[\r\n]+ *([^ ]*)', out.decode("utf-8"))
    project.remoteBranch = match.group(1)
    # Sync owners github repository main branch from modbus2mqtt main branch
    ownerrepo = project.owner + '/' + project.name
    executeSyncCommand( ['gh','repo','sync', ownerrepo ,  '-b' , 'main' ]  ).decode("utf-8")
    project.localChanges = int(subprocess.getoutput('git status --porcelain| wc -l')) 
    # download all branches from owners github to local git
    executeSyncCommand(['git','switch', project.remoteBranch ]).decode("utf-8")
    executeSyncCommand(['git','switch', project.branch]).decode("utf-8")
    executeSyncCommand( ['git','merge', 'main'] ).decode("utf-8")
    out = executeSyncCommand(['git','diff', '--name-only','main' ]).decode("utf-8")
    project.gitChanges = out.count('\n')

def pushProject(project:Project):
    # push local git branch to remote servers feature branch
    executeSyncCommand(['git','push', 'origin', project.branch]).decode("utf-8")

def compareProject( project:Project):
    # compares git current content with remote branch 
    project.branch =  subprocess.getoutput('git rev-parse --abbrev-ref HEAD')
    showOrigin = executeCommand( [ 'git', '-v', 'show', 'origin' ])

    project.localChanges = int(subprocess.getoutput('git status --porcelain| wc -l'))
    js = ghcompare( project.name,"modbus2mqtt","main", project.owner + ":" + project.branch)
    cmpResult = json.loads(js)
    project.hasChanges =  cmpResult['status'] == 'ahead'
    
def createpullProject( project: Project, projectsList:Projects, pullProjects:ProjectList, pullText:PullTexts, issuenumber:int):
    args = []
    if pullText != None:
        args.append("-f"); args.append( "title=" + pullText.topic)
        args.append("-f"); args.append( "body=" + pullText.text)
        if pullText.draft == False:
            args.append("-f"); args.append( 'draft=false')
        else:
            args.append("-f"); args.append( 'draft=true' )    
    else:
        args.append("-f"); args.append( "issue=" + str( issuenumber))
        args.append("-f"); args.append( 'draft=false')
    args.append("-f"); args.append( "head=" + project.owner + ":" + project.branch)
    args.append("-f"); args.append( "base=main")  
    try:      
        js = json.loads(ghapi('POST','/repos/'+ projectsList.owner +'/' + project.name + '/pulls',args))
        # Append "requires:" text
        project.pullrequestid = js['id']
    except SyncException as err:
        if len(args) and err.args[1] != "":
            js = json.loads(err.args[1])
            if js['errors'][0]['message'].startswith("A pull request already exists for"):
                eprint( js['errors'][0]['message']  + ". Continue...")
                project.pullrequestid = getPullrequestId(project,projectsList)
                return


   
def newBranch(project:Project, branch:str):
    try:
        executeSyncCommand(['git','show-ref','--quiet','refs/heads/' + branch])
    except:
        executeSyncCommand(['git','checkout','-b', branch])
    executeSyncCommand(['git','switch', branch])
    executeSyncCommand(['git','fetch'])
    
def getPullRequests(project:Project, projects:Projects):
    pullrequest = getRequiredPullrequests(project, projects)

def checkFileExistanceInGithubBranch(owner, repo, branch, file):
    result = json.loads(ghapi('GET','/repos/'+ owner +'/' + repo + '/git/trees/'+ branch +'?recursive=true'))
    tree = result['tree']
    for o in tree:
        if o['path'] == file:
            return True
    return False

def checkFileExistanceInGithubPullRequest(owner, repo, pullnumber, file):
    result = json.loads(ghapi('GET','/repos/'+ owner +'/' + repo + '/pulls/'+ pullnumber +'/files'))
    for o in result:
        if o['filename'] == file:
            return True
    return False

def readpulltextProject(project:Project):
    out = executeSyncCommand(['git','log','main...' + project.branch , '--pretty=BEGIN%s%n%b%nEND']).decode("utf-8")
    project.pulltexts = []
    while True:
        posBegin = out.find("BEGIN")
        posEnd = out.find("\nEND")
        commit = out[posBegin+5:posEnd]
        out = out[posEnd+4:]
        if posBegin != -1 and posEnd != -1:
            match = re.search(r'\[(bug|feature)\]([^\n]+)\n([\s\S]*)', commit)
            if match:
                pt = PullTexts(match.groups()[0],  match.groups()[1])
                if 3 == len(match.groups()):
                    pt.text = match.groups()[2]
                project.pulltexts.append(pt)
            
        if re.search(r'\s*$', out):
            break;

def getPullrequestId(project:Project, projects:Projects):
    js = json.loads(executeSyncCommand([ "gh", "pr", "list" , 
        "-R", projects.owner + "/" + project.name,
        "--json", "number" ,
        "--json", "headRefName",
        "--json", "author"  ]))
    if len(js) > 0:
        for entry in js:
            if entry['author']['login'] == project.owner and entry['headRefName'] == project.branch: 
                return js[0]["number"]
    return None
def getpulltext( project:Project, baseowner:str, pullrequestid:int = None)->str:
    if pullrequestid == None:
        pullrequestid = project.pullrequestid
    if pullrequestid != None and pullrequestid >0:
        js = json.loads(executeSyncCommand([ "gh", "pr", "view" , str( pullrequestid), 
            "-R", baseowner + "/" + project.name,
            "--json", "body"  ]))
        return  js['body']
    return None

requiredProjectsRe = r"\s*required PRs: (.*)\s*"

def getPullrequestFromString(prname:str )->typing.Dict[str,int]:
    pr = prname.split(':')
    if len(pr) != 2:
        raise SyncException("Invalid format for pull request (expected: <project>:<pull request number>)")
    return { "name":pr[0], "number":int(pr[1])}

def getRequiredPullrequests( project:Project, baseowner:str, pullrequest:str)->list[typing.Dict[str,int]]:
    pr = getPullrequestFromString(pullrequest)
    text = getpulltext( project, baseowner, pr["number"] )
    rc:list[typing.Dict[str,int]] = []      
    if( text != None):
        match = re.search( requiredProjectsRe, text)
        if len(match.groups()) == 1:
            prtexts = match.groups()[0].split(', ')
            for prtext in prtexts:
                pr = prtext.split(':')
                if len(pr) == 2:
                    rc.append({ "name":pr[0], "number":int(pr[1])})
    return rc

def updatepulltextProject(project:Project, projectsList: Projects, pullProjects:ProjectList, pullText:str):
    requiredText = "required PRs: "
    for p in pullProjects:
        requiredText += p.name + ":" + str(p.pullrequestid) + ", "
    if requiredText.endswith(", "):
        requiredText = requiredText[:-2]
    pulltext = getpulltext(project, projectsList.owner)
    if pulltext != None:
        pulltext = re.sub(
           requiredProjectsRe, 
           "", 
           pulltext)
        eprint( pulltext)
        args = [ "gh", "pr", "edit", str( project.pullrequestid), 
            "-R", projectsList.owner + "/" + project.name,
            "--body", pulltext + "\n" + requiredText ]
        eprint(' '.join(args))
        executeSyncCommand(args)

def dependenciesProject(project:Project,  projectsList: Projects,dependencytype: str, prProject:Project = None):
    if prProject == None:
        SyncException("pull requires pull request parameter -r")             
    npminstall =['npm', 'install']
    pkgjson = []
    with open('package.json') as json_data:
        pkgjson = json.load( json_data)
    prs = getRequiredPullrequests(prProject, projectsList.owner, prProject.name + ":" + str(prProject.pullrequestid))
                        
    for pr in prs:
        githubName = 'github:'+ projectsList.owner +'/' + pr['name']
        package = '@' + projectsList.owner+ '/' +  pr['name']
        
        if 'dependencies' in pkgjson and package in pkgjson['dependencies'].keys():
            match dependencytype:
                case "local":
                    npminstall.append( os.path.join('..',project.name))
                case "remote":
                    if checkFileExistanceInGithubBranch('modbus2mqtt', pr['name'],'main', 'package.json'):
                        npminstall.append(  githubName)
                    else:
                        eprint("package.json is missing in modbus2mqtt/" + project.name
                        + ".\nUnable to set remote reference in " + project.name + '/package.json'
                        + "\nContinuing with invalid reference")
                case "pull":
                    if checkFileExistanceInGithubPullRequest('modbus2mqtt', pr['name'],str(pr['number']), 'package.json'):   
                        npminstall.append(  githubName + '#pull/' + str(pr['number']) + '/head')  
                    else:
                        eprint("package.json is missing in modbus2mqtt/" + pr['name']
                        + ".\nUnable to set remote reference in " + pr['name'] + '/package.json'
                        + "\nContinuing with invalid reference")
    executeSyncCommand(npminstall)

projectFunctions = {
    'compare' : compareProject,
    'sync' : syncProject,
    'push' : pushProject,
    'createpull' : createpullProject,
    'newbranch': newBranch,
    'readpulltext': readpulltextProject,
    'dependencies': dependenciesProject,
    'updatepulltext': updatepulltextProject,
 
}


def doWithProjects( projects:Projects, command:str, *args:Any ): 
    pwd = os.getcwd()
    for project in projects.projects:
        os.chdir(project.name)
        try:
            projectFunctions[command]( project, *args)
        finally:
            os.chdir(pwd)

