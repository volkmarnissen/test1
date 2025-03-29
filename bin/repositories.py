#!/usr/bin/env python3
from dataclasses import dataclass
from enum import Enum
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
import time
from threading import Thread

@dataclass
class PullTexts:
    type: str= ""
    topic: str= ""
    text: str = ""
    draft: bool = True

currentRepository = "unknown"    

class TestStatus(Enum):
    running = 1
    failed = 2
    success = 3
    allfailed = 4
    notstarted = 0

@dataclass
class PullRequest:
    name: str
    number: int

@functools.total_ordering
class Repository:      
    def __init__(self, name:str):
        self.name = name
        self.branch = None
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
    testStatus: TestStatus = TestStatus.notstarted

class Repositorys: 
    def __init__(self, para:Dict):
        self.owner = para['owner']
        self.repositorys = para['repositories']
    owner: str
    login:str
    repositorys: Any
    pulltext: PullTexts = None

def getGitPrefix( repositorys:Repositorys):
    eprint( repositorys.login )
    if repositorys.owner == repositorys.login:
        return "https://github.com/"
    else:
        return "git@github.com:"
    
class SyncException(Exception):
    pass

def eprint(*args, **kwargs):
    print(*args, file=sys.stderr, **kwargs)

def executeCommand(cmdArgs: list[str], *args, **kwargs)-> str:
    ignoreErrors = kwargs.get('ignoreErrors', None)
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

def executeSyncCommandWithCwd(cmdArgs: list[str], cwdP:str, *args, **kwargs)-> str:
            
    if cwdP == None:
        cwdP = os.getcwd()
    proc = subprocess.Popen(cmdArgs,
    cwd=cwdP,
    stdout=subprocess.PIPE,
 	stderr=subprocess.PIPE) 
    out, err = proc.communicate()
    proc.returncode
    if proc.returncode != 0:
        raise SyncException( cwdP +':'+ err.decode("utf-8"), ' '.join(cmdArgs), out.decode("utf-8"))
    if len(err)>0:    
        eprint(err.decode("utf-8"))
    return out

def executeSyncCommand(cmdArgs: list[str], *args, **kwargs)-> str:
    return executeSyncCommandWithCwd(cmdArgs, os.getcwd(), *args, **kwargs)
   
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
def json2Repositorys(dct:Any ):
    if 'name' in dct:
        p =   Repository( dct['name'])
        return p
    return dct

def isRepositoryForked( repositoryName )->bool:
    forked = json.loads(executeCommand(['gh', 'repo' , 'list', '--fork', '--json', 'name'] ))
    for repository in forked:
        if repository['name'] == repositoryName :
            return True
    return False
def forkRepository( repositoryName, owner ):
   
    if '' != executeSyncCommand(['gh', 'repo' , 'fork',  owner + '/' + repositoryName]):
            time.sleep(3)
def branchExists( branch):
    try:
        executeSyncCommand( ['git', 'branch', branch])
        return False
    except SyncException as err:
        return True
def readrepositorys(repositorysFile)->Repositorys:
    try:
        input_file = open (repositorysFile)
        jsonDict:Dict[str,Any] =  json.load(input_file, object_hook=json2Repositorys)
        js = json.loads(ghapi('GET', '/user'))
        p =  Repositorys(jsonDict)
        p.login = js['login']
        return p
    except Exception as e:
        print("something went wrong " , e)
def getLocalChanges()->int:
    return int(subprocess.getoutput('git status --porcelain| wc -l')) 

def getTestResultStatus(repositorys:Repositorys):
    failedCount = 0
    for p in repositorys.repositorys:
        if p.testStatus == TestStatus.failed:
            failedCount +=1
    if failedCount > 0:
        if failedCount == len(repositorys.repositorys):
            return TestStatus.allfailed
        else:
            return TestStatus.failed
    else:
        return TestStatus.success
def hasLoginFeatureBranch(repository:Repository, repositorys:Repositorys):
    try:
        if repository.branch == None:
            return False
        line= executeSyncCommand(['git', 'ls-remote', '--heads', repositorys.login,  'refs/heads/' + repository.branch]).decode("utf-8")
        if len(line)> 0:
            return True
        return False
    except SyncException as err:
        return False        
def checkRemote( remote:str):
        out = executeSyncCommand(['git', 'remote','-v',]).decode("utf-8")
        return re.match(r'^' + remote, out)

def addRemote(repositories:Repositorys, repository:Repository, origin:str):
     cmd = ['git', 'remote', 'add', origin, getGitPrefix(repositories)  + origin + '/' + repository.name + '.git' ]
     executeSyncCommand(cmd)
def setUrl(repository:Repository, repositorys:Repositorys):
    origins = [repositorys.owner]
    if isRepositoryForked( repository.name):
        origins.append(repositorys.login)
        if hasLoginFeatureBranch(repository, repositorys):
            origins.append(repositorys.login)

    for origin in origins:
        if not checkRemote(origin):
            addRemote(repositorys,repository, origin)
    if hasLoginFeatureBranch(repository, repositorys):
        executeCommand([ 'git','fetch' , origin, repository.branch ])
        executeSyncCommand([ 'git','branch','--set-upstream-to='+ repositorys.login + '/' + repository.branch] )
    else:
        executeSyncCommand([ 'git','fetch', repositorys.owner , 'main'] )
        executeSyncCommand([ 'git','branch','--set-upstream-to='+ repositorys.owner + '/main'] )

   
def sendTestStatus( repositorys:Repositorys, status:TestStatus, update:bool=True):
    try:
        if repositorys.owner != repositorys.login:
            eprint( "Only the owner of the repos is allowed to update pull requests. No updates sent, but tests will be executed")
        statusStr = "No tests"
        match( status):
            case TestStatus.running: 
                statusStr = '# Tests are running ...'
            case TestStatus.success: 
                statusStr = '# Tests successful'
            case TestStatus.failed: 
                statusStr = '# Some Tests failed'
            case TestStatus.allfailed: 
                statusStr = '# All Tests failed'

        for p in repositorys.repositorys:
            if p.pullrequestid != None:
                if update:
                    executeSyncCommand(['gh', repositorys.owner + '/' + p.name , 'pr', 'comment', '--edit-last', '-b', statusStr ])
                else:
                    executeSyncCommand(['gh', repositorys.owner + '/' + p.name, 'pr', 'comment', '-b', statusStr ])
    except:
        eprint("Unable to send status to Pull Requests")
        #This will be ignored. The test results will also be 

@dataclass
class Checkrun:
    completed: bool
    success: bool

def getLastCheckRun(repositories:Repositorys,repository:Repository, branch:str)->Checkrun:
    js = json.loads(ghapi('GET', '/repos/' + repositories.owner +'/' + repository.name + '/commits/' + branch + '/check-runs?filter=latest').decode('utf-8'))
    if js['total_count'] != 1:
        raise SyncException( "Invalid number of check runs for " + '/'.join([repositories.owner , repository.name, branch]) + ': ' + js['total_count'])
    checkrunjs = js["checkruns"][0]
    return Checkrun(checkrunjs['status'] ==  "completed", checkrunjs["conclusion"] == "success")
              
def waitForMainTestPullRequest(repositories:Repositorys, mainTestPullRequest:PullRequest):
    eprint( "waiting for " + mainTestPullRequest.name + ":" + mainTestPullRequest.number)
    for mr in repositories.repositorys:
        if mr.name == mainTestPullRequest.name:
            while  True:
                js = getPullrequestId(mr,repositories,['state','headRefName'])
                match ( js['state'] ):
                    case 'OPEN'| 'APPROVED':  
                        eprint( "state " + js['state'])
                        checkrun = getLastCheckRun(repositories, mr, js['headRefName'] )
                        if checkrun.completed:
                            if checkrun.success:
                                eprint( mainTestPullRequest.name + ":" + mainTestPullRequest.number + " finished with success")
                                print("status=success" )
                                return
                            else:
                                eprint( mainTestPullRequest.name + ":" + mainTestPullRequest.number + " finished with failure")
                                print("status=failure" )
                                return
                    case _:
                        # try again later
                        time.sleep(30)
    # check run not found or other issues. It should stop with exit() when checkrun is finished
    SyncException( "Unable validate check run for pull Request " + mainTestPullRequest.name + ":" +  mainTestPullRequest.number )

def testRepositories(repositoriesFile:str):
            eprint( executeSyncCommand(["bin/testall.py", repositoriesFile]).decode("utf-8"))

# syncs main from original github source to local git branch (E.g. 'feature')
def syncRepository(repository: Repository, repositorys:Repositorys):
    repository.isForked = isRepositoryForked(repository.name)
    repository.branch =  subprocess.getoutput('git rev-parse --abbrev-ref HEAD')
    setUrl(repository,repositorys)
    
    js = json.loads(ghapi('GET', '/user'))
    out = executeCommand(['git','remote','show','origin'])
    match = re.search(r'.*Push *URL:[^:]*:([^\/]*)', out.decode("utf-8"))
    match = re.search(r'.*Remote[^:]*:[\r\n]+ *([^ ]*)', out.decode("utf-8"))
    repository.remoteBranch = match.group(1)
    # Sync owners github repository main branch from modbus2mqtt main branch
    # Only the main branch needs to be synced from github
    executeSyncCommand(['git','switch', 'main' ]).decode("utf-8")
    # ghapi('GET', ownerrepo+ '/merge-upstream', '-f', 'branch=main'
    # Is is not neccessary to update the main branch in forked repository, because the main branch's origin points to owner
    if repository.isForked:
        executeSyncCommand( ['gh','repo','sync', repositorys.login + '/' + repository.name ,  '-b' , 'main' ]  ).decode("utf-8")
        # download all branches from owners github to local git main branch
        try:
            ghapi('GET', '/repos/' + repositorys.login + '/' + repository.name + '/branches/' + repository.branch)
            executeSyncCommand(['git','switch', repository.branch]).decode("utf-8")
            executeSyncCommand(['git','branch','--set-upstream-to='+ repositorys.login +'/' + repository.branch, repository.branch ])
            executeSyncCommand(['git','pull','--rebase']).decode("utf-8")
        except SyncException as err:
            
            if  err.args[0] != "":
                if  "fatal: the requested upstream branch" in  err.args[0]:
                    executeSyncCommand(['git','fetch', 'modbus2mqtt']).decode("utf-8")
                    executeSyncCommand(['git','branch','--set-upstream-to='+ repositorys.owner +'/main' ])
                else:
                    js = json.loads(err.args[2])
                    if not js['message'].startswith("Branch not found"):
                        raise err
                    else:
                        executeSyncCommand(['git','branch','--set-upstream-to='+ repositorys.login +'/main', repository.branch ])
    else:
        executeSyncCommand(['git','switch', repository.branch]).decode("utf-8")
        executeSyncCommand(['git','pull', '--rebase']).decode("utf-8")
   
    repository.localChanges = getLocalChanges()
    executeSyncCommand( ['git','merge',  repositorys.owner +'/main'] ).decode("utf-8")
    out = executeSyncCommand(['git','diff', '--name-only','main' ]).decode("utf-8")
    repository.gitChanges = out.count('\n')

# syncs main from original github source to local git branch (E.g. 'feature')
def syncpullRepository(repository: Repository, repositorys:Repositorys, prs:list[PullRequest], branch:str):
    executeSyncCommand(['git','switch', 'main'])
    for pr in prs:
        found = False
        if not found and repository.name == pr.name:
            found = True
            checkRemote(repositorys.owner)
            branch = 'pull'+ str(pr.number)
            executeSyncCommand(['git', 'fetch', repositorys.owner, 'pull/' + str(pr.number)+ '/head:'+ branch ])
            executeSyncCommand(['git','switch', branch])
    if not found:
        #sync to main branch
        executeSyncCommand(['git', 'fetch', repositorys.owner, 'main'])
        executeSyncCommand(['git', 'checkout', 'main'])

def pushRepository(repository:Repository, repositorys:Repositorys):
    # Check if login/repository repository exists in github
    if repository.gitChanges == 0:
        return
    
    if not isRepositoryForked( repository.name):
        forkRepository(repository.name, repositorys.owner)
        executeSyncCommand(['git', 'remote', 'set-url', repositorys.login, getGitPrefix(repositorys)  + repositorys.login + '/'+ repository.name + '.git' ])
    executeSyncCommand(['git','switch', repository.branch])
    # push local git branch to remote servers feature branch
    executeSyncCommand(['git','push', repositorys.owner, repository.branch]).decode("utf-8")

def compareRepository( repository:Repository, repositorys:Repositorys):
    # compares git current content with remote branch 
    repository.branch =  subprocess.getoutput('git rev-parse --abbrev-ref HEAD')
    showOrigin = executeCommand( [ 'git', '-v', 'show', 'origin' ])
    repository.hasChanges = False
    repository.localChanges = int(subprocess.getoutput('git status --porcelain| wc -l'))

    # No remote branch compare main and feature branch with git
    out = executeSyncCommand(['git','diff', 'main']).decode("utf-8")
    repository.hasChanges = out.count('\n') > 0

def createpullRepository( repository: Repository, repositorysList:Repositorys, pullRepositorys, pullText:PullTexts, issuenumber:int):
    if repository.gitChanges == 0:
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
    args.append("-f"); args.append( "head=" + repositorysList.login + ":" + repository.branch)
    #args.append("-f"); args.append( "head=" + repository.branch)
    args.append("-f"); args.append( "base=main")  
    try:      
        js = json.loads(ghapi('POST','/repos/'+ repositorysList.owner +'/' + repository.name + '/pulls',args))
        # Append "requires:" text
        repository.pullrequestid = js['number']
    except SyncException as err:
        if len(args) and err.args[0] != "":
            js = json.loads(err.args[1])
            if js['errors'][0]['message'].startswith("A pull request already exists for"):
                eprint( js['errors'][0]['message']  + ". Continue...")
                repository.pullrequestid = getPullrequestId(repository,repositorysList)
                return


   
def newBranch(repository:Repository, branch:str):
    try:
        executeSyncCommand(['git','show-ref','--quiet','refs/heads/' + branch])
    except:
        executeSyncCommand(['git','checkout','-b', branch ])
    executeSyncCommand(['git','switch', branch])
    executeSyncCommand(['git','fetch'])
    
def getPullRequests(repository:Repository, repositorys:Repositorys):
    pullrequest = getRequiredPullrequests(repository, repositorys)

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

def readpulltextRepository(repository:Repository):
    out = executeSyncCommand(['git','log','main...' + repository.branch , '--pretty=BEGIN%s%n%b%nEND']).decode("utf-8")
    repository.pulltexts = []
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
                repository.pulltexts.append(pt)
            
        if re.search(r'\s*$', out):
            break;

def getPullrequestId(repository:Repository, repositorys:Repositorys, additionalFields:list[str] = None):
    cmd = [ "gh", "pr", "list" , 
        "-R", repositorys.owner + "/" + repository.name,
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
            if entry['author']['login'] == repositorys.login and entry['headRefName'] == repository.branch: 
                if additionalFields == None:
                    return js[0]["number"]
                else:
                    return js[0]
    return None
def getpulltext( repository:Repository, baseowner:str, pullrequestid:int = None)->str:
    if pullrequestid == None:
        pullrequestid = repository.pullrequestid
    if pullrequestid != None and pullrequestid >0:
        js = json.loads(executeSyncCommand([ "gh", "pr", "view" , str( pullrequestid), 
            "-R", baseowner + "/" + repository.name,
            "--json", "body"  ]))
        return  js['body']
    return None

requiredRepositorysRe = r"\s*required PRs: (.*)\s*"

def getPullrequestFromString(prname:str )->PullRequest:
    pr = prname.split(':')
    if len(pr) != 2:
        raise SyncException("Invalid format for pull request (expected: <repository>:<pull request number>)")
    return PullRequest(pr[0],int(pr[1]))

def getRequiredReposFromPRDescription(prDescription:str,pullrequest:PullRequest)->list[PullRequest]:
    rc:list[PullRequest] = []      
    if( prDescription != None):
        match = re.search( requiredRepositorysRe, prDescription)
        if None != match and len(match.groups()) == 1:
            prtexts = match.groups()[0].split(', ')
            for prtext in prtexts:
                prx = prtext.split(':')
                if len(prx) == 2:
                    rc.append(PullRequest(prx[0],int(prx[1])))
        else:
            rc.append(pullrequest)
    return rc

def getRequiredPullrequests( repository:Repository, pullrequest:PullRequest, pulltext:str = None, owner:str=None )->list[PullRequest]:
    if pulltext == None and owner != None:
        pulltext = getpulltext( repository, owner, pullrequest.name, pullrequest.number )
    return getRequiredReposFromPRDescription(pulltext,pullrequest)

def updatepulltextRepository(repository:Repository, repositorysList: Repositorys, pullRepositorys):
    requiredText = "required PRs: "
    for p in pullRepositorys:
        requiredText += p.name + ":" + str(p.pullrequestid) + ", "
    if requiredText.endswith(", "):
        requiredText = requiredText[:-2]
    pulltext = getpulltext(repository, repositorysList.owner)
    if pulltext != None:
        pulltext = re.sub(
           requiredRepositorysRe, 
           "", 
           pulltext)
    eprint( pulltext)
    args = [ "gh", "pr", "edit", str( repository.pullrequestid), 
            "-R", repositorysList.owner + "/" + repository.name,
            "--body", pulltext + "\n" + requiredText ]
    executeSyncCommand(args)
def readPackageJson( dir:str)->Dict[str,any]:
    try:
        with open(dir) as json_data:
            return  json.load( json_data)
    except Exception as err:
        eprint("Exception read " )
        msg = str(err.args)
        raise SyncException("Try to open package.json in " + os.getcwd() + '\n' +  msg)
def updatePackageJsonReferences(repository:Repository,  repositorysList: Repositorys,dependencytype: str, prRepository:Repository):
    prs:list[PullRequest] = []
    if dependencytype == 'pull':
        prs = getRequiredPullrequests(prRepository,  PullRequest(prRepository.name ,prRepository.pullrequestid), owner=repositorysList.owner)
        if prRepository == None:
            SyncException("pull requires pull request parameter -r")
        else: # do it for all repositorys
            for pr in repositorysList.repositorys:
                prs.append(PullRequest(pr.name, pr.pullrequestid))         
    npminstallargs = []
    npmuninstallargs = []
    pkgjson = readPackageJson('package.json')
    
    for pr in prs:
         # restrict to open PR's
            
        package = '@' + repositorysList.owner+ '/' +  pr['name']
        
        if 'dependencies' in pkgjson and package in pkgjson['dependencies'].keys():
            pRepository = Repository(pr['name'])
            pRepository.branch = repository.branch
            js = getPullrequestId( pRepository,repositorysList,["state"])
            # If PR is no more open, use main branch instead of PR
            if ( js == None and dependencytype == 'local') or( dependencytype == 'pull' and js['state'] not in ['OPEN', 'APPROVED']):
                dependencytype ='remote'
                   
            match dependencytype:
                case "local":
                    npminstallargs.append( os.path.join('..',pr.name))
                    npmuninstallargs.append( package )
                case "remote":
                    # for testing: Use login instead of owner
                    # In production owner == login
                    githubName = 'github:'+ repositorysList.owner +'/' + pr['name']
                    if checkFileExistanceInGithubBranch('modbus2mqtt', pr['name'],'main', 'package.json'):
                        npminstallargs.append(  githubName)
                        npmuninstallargs.append( package )
                    else:
                        eprint("package.json is missing in modbus2mqtt/" + pr['name'] +"#main"
                        + ".\nUnable to set remote reference in modbus2mqtt/" + repository.name 
                        + "\nContinuing with invalid reference")
                case "release":
                    # read package.json's version number build version tag
                    versionTag = "v" + readPackageJson(os.path.join('..', pr['name'] ,'package.json'))['version']
                    releaseName = 'github:'+ repositorysList.login +'/' + pr['name']+ '#' +versionTag
                    npminstallargs.append(  releaseName)
                    npmuninstallargs.append( package )                    
                case "pull":
                    githubName = 'github:'+ repositorysList.owner +'/' + pr['name']
                    newgithubName = githubName + '#pull/' + str(pr['number']) + '/head'
                    if checkFileExistanceInGithubPullRequest('modbus2mqtt', pr['name'],str(pr['number']), 'package.json'):
                        npminstallargs.append(  newgithubName )  
                        npmuninstallargs.append( package )
                    else:
                        eprint("package.json is missing in " + newgithubName
                        + ".\nUnable to set remote reference                                                                                                                                                                                                                                in modbus2mqtt/" + pr['name'] + '/package.json'
                        + "\nContinuing with invalid reference")
    if len(npmuninstallargs ) > 0:
        executeSyncCommand(["npm", "uninstall"] + npmuninstallargs)
    try:        
        executeSyncCommand(["npm", "install"]  + npminstallargs)
        return len(npminstallargs ) > 0
    except Exception as err:
        eprint("npm cache exceptions can happen if the github url in dependencies is wrong!")
        raise err
    
def tagExists(tagname:str)->bool:
    try:
        return executeSyncCommand(["git","tag", "-l", tagname]).decode("utf-8").count('\n') > 0
    except Exception as err:
        eprint( "tag doesn't exists", err.args[0])
        return False

def ensureNewPkgJsonVersion():
    versionTag = "v" + readPackageJson('package.json')['version']        
    if tagExists(versionTag):
        executeSyncCommand(["npm", "--no-git-tag-version", "version", "patch"])
        return "v" + readPackageJson('package.json')['version']        
    return versionTag

def dependenciesRepository(repository:Repository,  repositorysList: Repositorys,dependencytype: str, prRepository:Repository = None):

    if dependencytype == 'release':
        # find unreleased commits
        changedInMain = 0
        executeSyncCommand( ['git','switch', 'main'] )
        executeSyncCommand( ['git','pull','--rebase'] )
        try:
            sha = executeSyncCommand( ['git','merge-base','--fork-point', 'release' ] ).decode("utf-8")
            sha = sha.replace('\n','')
            out:str = executeSyncCommand(['git','diff', '--name-status', sha ]).decode("utf-8")
            changedInMain = out.count('\n')
            js = ghcompare( repository.name,repositorysList.owner,"main", repositorysList.owner + ":" + repository.branch)
            cmpResult = json.loads(js)
            changedInMain +=  int(cmpResult['behind_by'])

        except SyncException as err:
            if err.args[0] != '': # Wrong return code from git merge-base but no changes
                raise err
                
        versionTag = ""
        needsNewRelease = False
        if changedInMain >0:
            # Check in version number to main branch
            versionTag = ensureNewPkgJsonVersion()
            if  getLocalChanges() > 0:
                executeSyncCommand( ["git", "add", "."])
                executeSyncCommand( ["git", "commit", "-m" , "Update npm version number " + versionTag] )
                executeSyncCommand( ["git", "pull", "-X", "theirs"] )
                executeSyncCommand( ["git", "push" , "-f", "origin", "HEAD"])
                needsNewRelease = True

        executeSyncCommand( ['git','switch', 'release'] )
        executeSyncCommand( ["git", "pull", "-X", "theirs"] )
        executeSyncCommand( ['git','merge', '-X','theirs', 'main'] )
        updatePackageJsonReferences(repository, repositorysList, dependencytype, prRepository)    
        if  getLocalChanges() > 0:
            # makes sure, the version number in local pgkJson is new
            # local changes are from updated dependencies            
            versionTag = ensureNewPkgJsonVersion()
            executeSyncCommand(["git", "add", "."])
            executeSyncCommand(["git", "commit", "-m" , "Release " + versionTag] )
            needsNewRelease = True
        # May be the version number is up to date, but the tag doesn't exist
        versionTag = "v" + readPackageJson('package.json')['version']
        if  not tagExists(versionTag):
                executeSyncCommand(["git", "tag", versionTag] )
                if needsNewRelease:
                    executeSyncCommand(["git", "push", "--atomic", "-f", "origin" , "release", versionTag])
                else:
                    executeSyncCommand(["git", "push", "origin", "tag", versionTag])
                eprint( "Released " + repository.name + ":" + versionTag)
        else:
            if needsNewRelease:
                raise SyncException( "Release failed: Tag '" + versionTag + "' exists in " + repository.name )
    else:
        updatePackageJsonReferences(repository, repositorysList, dependencytype, prRepository)
        repository.localChanges = getLocalChanges()
        if repository.localChanges > 0:
            raise SyncException("File(s) have been updated in " + repository.name + ".\nThere are local changes.\nPlease commit them first")
        
def prepareGitForReleaseRepository(repository:Repository,  repositorysList: Repositorys):
    if repositorysList.login != repositorysList.owner:
       raise SyncException("Release is allowed for " + repositorysList.owner + " only")
    js = executeSyncCommand(['git', 'remote', '-v']).decode("utf-8")
    match = re.search(r'' + repositorysList.owner + '/', js)
    if not match:
       raise SyncException("Git origin is not " + repositorysList.owner + '/' + repository.name )
    executeSyncCommand(['git', 'switch', 'release']).decode("utf-8")
    repository.branch = "release"
def npminstallRepository(repository:Repository):
    executeSyncCommand(['npm','install'])
    
repositoryFunctions = {
    'compare' : compareRepository,
    'sync' : syncRepository,
    'npminstall':npminstallRepository,
    'syncpull': syncpullRepository,
    'test': testRepository,
    'push' : pushRepository,
    'createpull' : createpullRepository,
    'newbranch': newBranch,
    'readpulltext': readpulltextRepository,
    'dependencies': dependenciesRepository,
    'updatepulltext': updatepulltextRepository,
    'prepareGitForRelease': prepareGitForReleaseRepository,
}


def doWithRepositorys( repositorys:Repositorys, command:str, *args:Any ): 
    eprint("step: " + command, sep=' ', end='', flush=True )
    pwd = os.getcwd()
    for repository in repositorys.repositorys:
        global currentRepository 
        eprint( repository.name)
        currentRepository = repository.name
        eprint(" " + currentRepository, sep=' ', end='', flush=True )
        os.chdir(repository.name)
        eprint(os.getcwd())
        try:
            repositoryFunctions[command]( repository, *args)
        finally:
            os.chdir(pwd)
    eprint("")

