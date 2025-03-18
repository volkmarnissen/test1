#!/usr/bin/env python3
from dataclasses import dataclass
import functools
import io
import json
import argparse
import os
import subprocess
import sys
import re
import time
from typing import Any, Dict
import typing
from threading import Thread

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
    name: str
    branch: str
    isForked: bool = False
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
    login:str
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

class StreamThread ( Thread ):
    def __init__(self, buffer):
        Thread.__init__(self)
        self.buffer = buffer
    def run ( self ):
        while 1:
            line = self.buffer.readline()
            eprint(line,end="")
            sys.stderr.flush()
            if line == '':
                break
            
def executeSyncCommand(cmdArgs: list[str], *args, **kwargs)-> str:
    proc = subprocess.Popen(cmdArgs,
	cwd=os.getcwd(),
 	stdout=subprocess.PIPE,
 	stderr=subprocess.PIPE) 
    out, err = proc.communicate()
    proc.returncode
    if proc.returncode != 0:
        raise SyncException( ' '.join(cmdArgs), out.decode("utf-8"),err.decode("utf-8"))
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
        p =   Project( dct['name'])
        return p
    return dct

def isProjectForked( projectName )->bool:
    forked = json.loads(executeCommand(['gh', 'repo' , 'list', '--fork', '--json', 'name'] ))
    for project in forked:
        if project['name'] == projectName :
            return True
    return False
def forkProject( projectName, owner ):
   
    if '' != executeSyncCommand(['gh', 'repo' , 'fork',  owner + '/' + projectName]):
            time.sleep(3)

def readprojects(projectsFile)->Projects:
    try:
        input_file = open (projectsFile)
        jsonDict:Dict[str,Any] =  json.load(input_file, object_hook=json2Projects)
        js = json.loads(ghapi('GET', '/user'))
        p =  Projects(jsonDict)
        p.login = js['login']
        return p
    except Exception as e:
        print("something went wrong " , e)
def getLocalChanges()->int:
    return int(subprocess.getoutput('git status --porcelain| wc -l')) 
def testProject(project: Project, projects:Projects):
    executeSyncCommand(["npm", "run", "test"])   

# syncs main from original github source to local git branch (E.g. 'feature')
def syncProject(project: Project, projects:Projects):
    project.isForked = isProjectForked(project.name)
    if project.isForked:
        executeSyncCommand( ['git', 'remote', 'set-url', 'origin', 'git@github.com:' + projects.login + '/' + project.name + '.git' ]  )
    else:
        executeSyncCommand(['git', 'remote', 'set-url', 'origin', 'git@github.com:' + projects.owner + '/'+ project.name + '.git' ])

    project.branch =  subprocess.getoutput('git rev-parse --abbrev-ref HEAD')
    js = json.loads(ghapi('GET', '/user'))
    out = executeCommand(['git','remote','show','origin'])
    match = re.search(r'.*Push *URL:[^:]*:([^\/]*)', out.decode("utf-8"))
    match = re.search(r'.*Remote[^:]*:[\r\n]+ *([^ ]*)', out.decode("utf-8"))
    project.remoteBranch = match.group(1)
    # Sync owners github repository main branch from modbus2mqtt main branch
    # Only the main branch needs to be synced from github
    executeSyncCommand(['git','switch', 'main' ]).decode("utf-8")
    # ghapi('GET', ownerrepo+ '/merge-upstream', '-f', 'branch=main'
    if project.isForked:
        executeSyncCommand( ['gh','repo','sync', projects.login + '/' + project.name ,  '-b' , 'main' ]  ).decode("utf-8")
        # download all branches from owners github to local git main branch
        try:
            ghapi('GET', '/repos/' + projects.login + '/' + project.name + '/branches/' + project.branch)
            executeSyncCommand(['git','switch', project.branch]).decode("utf-8")
            executeSyncCommand(['git','branch','--set-upstream-to=origin/' + project.branch, project.branch ])
            executeSyncCommand(['git','pull']).decode("utf-8")
        except SyncException as err:
            if  err.args[1] != "":
                js = json.loads(err.args[1])
                if not js['message'].startswith("Branch not found"):
                    raise err
                else:
                    executeSyncCommand(['git','branch','--set-upstream-to=origin/main', project.branch ])

    executeSyncCommand(['git','switch', project.branch]).decode("utf-8")
    project.localChanges = getLocalChanges()
    executeSyncCommand(['git','fetch']).decode("utf-8")
     
    executeSyncCommand( ['git','merge', 'main'] ).decode("utf-8")
    out = executeSyncCommand(['git','diff', '--name-only','main' ]).decode("utf-8")
    project.gitChanges = out.count('\n')

# syncs main from original github source to local git branch (E.g. 'feature')
def syncpullProject(project: Project, projects:Projects, prs:Dict[str,int], branch:str):
    executeSyncCommand(['git', 'remote', 'set-url', 'origin', 'git@github.com:' + projects.owner + '/'+ project.name + '.git' ])
                
    for pr in prs:
        found = False
        if not found and project.name == pr["name"]:
            found = True
            executeSyncCommand(['git', 'fetch' 'origin', 'pull/' + str(pr['number'])+ '/head:' + branch ])
            executeSyncCommand(['git','switch', branch])
    if not found:
        #sync to main branch
        executeSyncCommand(['git', 'fetch' 'origin', 'main'])
        executeSyncCommand(['git', 'checkout', 'main'])

def pushProject(project:Project, projects:Projects):
    # Check if login/project repository exists in github
    if project.gitChanges == 0:
        return
    
    if not isProjectForked( project.name):
        forkProject(project.name, projects.owner)

    js = executeSyncCommand(['git', 'remote', '-v']).decode("utf-8")
    match = re.search(r'' + projects.login + '/', js)
    if not match:
        executeSyncCommand(['git', 'remote', 'set-url', 'origin', 'git@github.com:' + projects.login + '/'+ project.name + '.git' ])

    # push local git branch to remote servers feature branch
    executeSyncCommand(['git','push', 'origin', project.branch]).decode("utf-8")

def compareProject( project:Project, projects:Projects):
    # compares git current content with remote branch 
    project.branch =  subprocess.getoutput('git rev-parse --abbrev-ref HEAD')
    showOrigin = executeCommand( [ 'git', '-v', 'show', 'origin' ])
    project.hasChanges = False
    project.localChanges = int(subprocess.getoutput('git status --porcelain| wc -l'))
    if project.isForked:
        js = ghcompare( project.name,projects.owner,"main", projects.login + ":" + project.branch)
        cmpResult = json.loads(js)
        project.hasChanges =  cmpResult['status'] == 'ahead'
    
def createpullProject( project: Project, projectsList:Projects, pullProjects:ProjectList, pullText:PullTexts, issuenumber:int):
    if project.gitChanges == 0:
        return
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
    args.append("-f"); args.append( "head=" + projectsList.login + ":" + project.branch)
    #args.append("-f"); args.append( "head=" + project.branch)
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

def getPullrequestId(project:Project, projects:Projects, additionalFields:list[str] = None):
    cmd = [ "gh", "pr", "list" , 
        "-R", projects.owner + "/" + project.name,
        "--json", "number" ,
        "--json", "headRefName",
        "--json", "author"  ]
    if additionalFields != None:
        for field in additionalFields:
            cmd.append("--json")
            cmd.append( field )
    js = json.loads(executeSyncCommand(cmd))
    if len(js) > 0:
        for entry in js:
            if entry['author']['login'] == projects.login and entry['headRefName'] == project.branch: 
                if additionalFields == None:
                    return js[0]["number"]
                else:
                    return js[0]
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
                prx = prtext.split(':')
                if len(prx) == 2:
                    rc.append({ "name":prx[0], "number":int(prx[1])})
        else:
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
        executeSyncCommand(args)
def readPackageJson( dir:str)->Dict[str,any]:
    try:
        with open(dir) as json_data:
            return  json.load( json_data)
    except Exception as err:
        msg = ""
        for arg in err.args:
            if type(arg) is str:
                msg = msg + arg
        raise SyncException("Try to open package.json in " + dir, msg)
def updatePackageJsonReferences(project:Project,  projectsList: Projects,dependencytype: str, prProject:Project):
    prs: list[Dict[str, int]] = []
    if dependencytype == 'pull':
        prs = getRequiredPullrequests(prProject, projectsList.owner, prProject.name + ":" + str(prProject.pullrequestid))
        if prProject == None:
            SyncException("pull requires pull request parameter -r")
    else: # do it for all projects
        for pr in projectsList.projects:
            prs.append({"name":pr.name, "number":pr.pullrequestid})           
    npminstall =['npm', 'install']
    npminstallargs = []
    npmuninstallargs = []
    pkgjson = readPackageJson('package.json')
    
    for pr in prs:
         # restrict to open PR's
        githubName = 'github:'+ projectsList.owner +'/' + pr['name']
            
        package = '@' + projectsList.owner+ '/' +  pr['name']
        
        if 'dependencies' in pkgjson and package in pkgjson['dependencies'].keys():
            pProject = Project(pr['name'])
            pProject.branch = project.branch
            js = getPullrequestId( pProject,projectsList,["state"])
            # If PR is no more open, use main branch instead of PR
            if ( js == None and dependencytype == 'local') or( dependencytype == 'pull' and js['state'] not in ['OPEN', 'APPROVED']):
                dependencytype ='remote'
                   
            match dependencytype:
                case "local":
                    npminstallargs.append( os.path.join('..',pr.name))
                    npmuninstallargs.append( package )
                case "remote":
                    if checkFileExistanceInGithubBranch('modbus2mqtt', pr['name'],'main', 'package.json'):
                        npminstallargs.append(  githubName)
                        npmuninstallargs.append( package )
                    else:
                        eprint("package.json is missing in modbus2mqtt/" + pr['name'] +"#main"
                        + ".\nUnable to set remote reference in modbus2mqtt/" + project.name 
                        + "\nContinuing with invalid reference")
                case "release":
                    # read package.json's version number build version tag
                    versionTag = "v" + readPackageJson(os.path.join('..', pr['name'] ,'package.json'))['version']
                    releaseName = 'github:'+ projectsList.owner +'/' + pr['name']+ '#' +versionTag
                    npminstallargs.append(  releaseName)
                    npmuninstallargs.append( package )                    
                case "pull":
                    newgithubName = githubName + '#pull/' + str(pr['number']) + '/head'
                    if checkFileExistanceInGithubPullRequest('modbus2mqtt', pr['name'],str(pr['number']), 'package.json'):
                        npminstallargs.append(  newgithubName )  
                        npmuninstallargs.append( package )
                    else:
                        eprint("package.json is missing in " + newgithubName
                        + ".\nUnable to set remote reference in modbus2mqtt/" + pr['name'] + '/package.json'
                        + "\nContinuing with invalid reference")
    if len(npmuninstallargs ) > 0:
        executeSyncCommand(["npm", "uninstall"] + npmuninstallargs)
    executeSyncCommand(npminstall + npminstallargs)
    return len(npminstallargs ) > 0
def tagExists(tagname:str)->bool:
    try:
        executeSyncCommand("git","tag", "-l", tagname)
        return True
    except:
        return False

def ensureNewPkgJsonVersion():
    versionTag = "v" + readPackageJson('package.json')['version']        
    if tagExists(versionTag):
        executeSyncCommand("npm", "--no-git-tag-version", "version", "patch")
        return "v" + readPackageJson('package.json')['version']        
    return versionTag

def dependenciesProject(project:Project,  projectsList: Projects,dependencytype: str, prProject:Project = None):
    updatePackageJsonReferences(project, projectsList, dependencytype, prProject)
    out = executeSyncCommand(['git','diff', '--name-only','main' ]).decode("utf-8")
    project.gitChanges = out.count('\n')

    if dependencytype == 'release':
        # find unreleased commits 
        out = executeSyncCommand(["git", "log", "--oneline", "--first-parent",  "main", "^release"])
        changedInMain = out.count('\n')
        if changedInMain >0:
            executeSyncCommand( ['git','merge', 'main'] )
            # makes sure, the version number in local pgkJson is new
            ensureNewPkgJsonVersion()
        # local changes are either new version number or updated dependencies
        if  getLocalChanges():
            versionTag = ensureNewPkgJsonVersion()
            executeSyncCommand("git", "add", ".")
            executeSyncCommand("git", "commit", "-m" , "Release " + versionTag )
        # May be the version number is up to date, but the tag doesn't exist
        versionTag = "v" + readPackageJson('package.json')['version']                    
        if  not tagExists(versionTag):
            executeSyncCommand("git", "tag", versionTag )
            executeSyncCommand("git", "push", "--tags", "origin" )
    else:
        project.localChanges = getLocalChanges()
        if project.localChanges > 0:
            raise SyncException("File(s) have been updated in " + project.name + ".\nThere are local changes.\nPlease commit them first")
def prepareGitForReleaseProject(project:Project,  projectsList: Projects):
    if projectsList.login != projectsList.owner:
       raise SyncException("Release is allowed for " + projectsList.owner + "only")
    js = executeSyncCommand(['git', 'remote', '-v']).decode("utf-8")
    match = re.search(r'' + projectsList.owner + '/', js)
    if not match:
       raise SyncException("Git origin is not " + projectsList.owner + '/' + project.name + "only")
    js = executeSyncCommand(['git', 'branch', '-v']).decode("utf-8")
    match = re.search(r'^\s*release', js)
    if not match:
        raise SyncException("Git remote branch is not 'release' in " + projectsList.owner + '/' + project.name + "only")
    
projectFunctions = {
    'compare' : compareProject,
    'sync' : syncProject,
    'syncpull': syncpullProject,
    'test': testProject,
    'push' : pushProject,
    'createpull' : createpullProject,
    'newbranch': newBranch,
    'readpulltext': readpulltextProject,
    'dependencies': dependenciesProject,
    'updatepulltext': updatepulltextProject,
    'prepareGitForRelease': prepareGitForReleaseProject,
}


def doWithProjects( projects:Projects, command:str, *args:Any ): 
    eprint("step: " + command )
    pwd = os.getcwd()
    for project in projects.projects:
        os.chdir(project.name)
        try:
            projectFunctions[command]( project, *args)
        finally:
            os.chdir(pwd)

