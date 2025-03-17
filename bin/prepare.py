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

def createPulls( projectsList:projects.Projects):
    # compareProjects(projects)
    projects.doWithProjects(projectsList,'sync', projectsList.login)
    projects.doWithProjects(projects,'compare')

parser = argparse.ArgumentParser()
parser.add_argument("-p", "--projects", help="projects.json file ",  nargs='?', default='projects.json', const='projects.json')
parser.add_argument("-b", "--branch", help="New Branch ",  nargs='?', default='main')
args = parser.parse_args()
projectsList = projects.readprojects(args.projects)
for project in projectsList.projects:   
    # fork will fail if project it is already forked.The error will be ignored
    owner = projectsList.login
    if not isProjectForked(project.name ):
        owner = projectsList.owner    
    if not os.path.exists( project.name ):
        projects.executeCommand(['git','clone', 'git@github.com:' + 
            owner + '/' +project.name + '.git' ])
projects.doWithProjects(projectsList,'newbranch', args.branch)
