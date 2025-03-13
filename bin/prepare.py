#!/usr/bin/env python3
import argparse
import json
import projects
import os
import time

def isProjectForked( projectName )->bool:
    forked = json.loads(projects.executeCommand(['gh', 'repo' , 'list', '--fork', '--json', 'name'] ))
    for project in forked:
        if project['name'] == projectName :
            return True
    return False

def createPulls( projectsList):
    # compareProjects(projects)
    projects.doWithProjects(projectsList,'sync')
    projects.doWithProjects(projects,'compare')

parser = argparse.ArgumentParser()
parser.add_argument("command", help="command [create: creates pull requests ]", choices=['create'], default='create')
parser.add_argument("owner", help="github owner name", type=str)
parser.add_argument("-p", "--projects", help="projects.json file ",  nargs='?', default='projects.json', const='projects.json')
parser.add_argument("-b", "--branch", help="New Branch ",  nargs='?', default='main')
args = parser.parse_args()
owner = args.owner
projectsList = projects.readprojects(args.projects)
for project in projectsList['projects']:   
    # fork will fail if project it is already forked.The error will be ignored
    if not isProjectForked(project['name'] ):
        if '' != projects.executeCommand(['gh', 'repo' , 'fork',  projectsList['owner'] + '/' + project['name']]):
            time.sleep(3)
        else:
            projects.eprint("Unable to fork project " + projectsList['owner'] + '/' + project['name'])
            exit(1)          
    if not os.path.exists( project['name'] ):
        if not os.path.exists( os.path.join( project['name'], '.git' )):
            projects.executeCommand(['git','clone', 'git@github.com:' + args.owner + '/' +project['name'] + '.git' ])
        else:
            projects.eprint( 'Directory ' + project['name'] + ' but .git directory does not exist. Remove the directory or use another root directory' )
projects.doWithProjects(projectsList,'newbranch', args.branch)
