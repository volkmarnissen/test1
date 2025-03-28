#!/usr/bin/env python3
import argparse
import json
import bin.repositories as repositories
import os
import time

def isProjectForked( projectName )->bool:
    forked = json.loads(repositories.executeCommand(['gh', 'repo' , 'list', '--fork', '--json', 'name'] ))
    for project in forked:
        if project['name'] == projectName :
            return True
    return False

def createPulls( projectsList:repositories.Projects):
    # compareProjects(projects)
    repositories.doWithProjects(projectsList,'sync', projectsList.login)
    repositories.doWithProjects(repositories,'compare')

parser = argparse.ArgumentParser()
parser.add_argument("-p", "--projects", help="projects.json file ",  nargs='?', default='projects.json', const='projects.json')
parser.add_argument("-b", "--branch", help="New Branch ",  nargs='?', default='main')
args = parser.parse_args()
projectsList = repositories.readprojects(args.projects)
for project in projectsList.projects:   
    # fork will fail if project it is already forked.The error will be ignored
    owner = projectsList.login
    if not isProjectForked(project.name ):
        owner = projectsList.owner    
    if not os.path.exists( project.name ):
        repositories.executeCommand(['git','clone', 'git@github.com:' + 
            owner + '/' +project.name + '.git' ])
repositories.doWithProjects(projectsList,'newbranch', args.branch)
