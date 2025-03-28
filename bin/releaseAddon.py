#!/usr/bin/env python3
import argparse
import os
import re
import json
import sys
import tarfile
import subprocess

import repositories
from typing import NamedTuple

server ='server'
hassioAddonRepository= 'hassio-addon-repository'

modbus2mqtt ='modbus2mqtt'
modbus2mqttLatest ='modbus2mqtt.latest'
configYaml='config.yaml'
dockerDir ='docker'
dockerFile = 'Dockerfile'

class StringReplacement(NamedTuple):
    pattern: str
    newValue:str

def getLatestClosedPullRequest(basedir, component ):
    return json.loads(repositories.executeSyncCommandWithCwd(['gh', 'pr', 'list', 
	    '-s' , 'closed' , '-L', '1', '--json', 'number'], os.path.join(basedir, component)))[0]['number']


def removeTag(basedir, component, tagname ):
    try:
        repositories.executeSyncCommandWithCwd(['git', 'push', '--delete', 
	    'origin' , tagname], os.path.join(basedir, component))
        repositories.eprint("tagname: !" + tagname + "!")
        repositories.executeSyncCommandWithCwd(['git', 'tag', '-d', tagname], os.path.join(basedir, component))
    except repositories.SyncException as err:
        repositories.eprint( err.args)


def getVersionForDevelopment(basedir, component):
    prnumber = getLatestClosedPullRequest(basedir, component)
    version = repositories.readPackageJson(os.path.join(basedir, component,'package.json'))['version']
    return version + "-pr" + str(prnumber)

def replaceStringInFile(inFile, outFile, replacements):
    for repl in replacements:
        repositories.eprint( "replacements: " , repl.pattern, repl.newValue)
    with open(inFile, 'r') as file:
        data = file.read()
        for repl in replacements:
            data = re.sub(rf"{repl.pattern}", repl.newValue,data)
        with open(outFile, 'w') as w:        
            w.write( data)

# runs in (@modbus2mqtt)/server
# updates config.yaml in (@modbus2mqtt)/hassio-addon-repository
def updateConfigAndDockerfile(basedir,version, replacements,replacementsDocker=None):
    sys.stderr.write("createAddonDirectory release " + basedir  + " " +  version + "\n")
    config = os.path.join(basedir,  configYaml)
    docker = os.path.join(basedir,  dockerFile)
    replaceStringInFile(config,config, replacements)
    if replacementsDocker != None:
        replaceStringInFile(docker, docker, replacementsDocker )
 

# publishes docker image from (@modbus2mqtt)/hassio-addon-repository
# docker login needs to be executed in advance 
def pusblishDocker(basedir, version):
    sys.stderr.write("publishDocker "  + basedir + " " + version)

parser = argparse.ArgumentParser()
parser.add_argument("-b", "--basedir", help="base directory of all repositories", default='.')
parser.add_argument("-R", "--ref", help="ref branch or tag ", default='refs/heads/main')
parser.add_argument("-r", "--release", help="builds sets version number in config.yaml", action='store_true')

args = parser.parse_args()
if not args.release:

    version = getVersionForDevelopment(args.basedir, 'server' )
    replacements = [
        StringReplacement(pattern='version: v[0-9.][^\n]*', newValue='version: v' +version + '\n'),
        ]
    updateConfigAndDockerfile(os.path.join(args.basedir, hassioAddonRepository,modbus2mqttLatest), version, replacements,replacements)
    print("TAG_NAME=v" + version)
else:
    repositories.executeSyncCommand(['rsync', '-avh', os.path.join(args.basedir,hassioAddonRepository,modbus2mqttLatest) + '/', os.path.join(args.basedir,hassioAddonRepository,modbus2mqtt) +'/', '--delete'])
        
    version = repositories.readPackageJson(os.path.join( args.basedir, 'server', 'package.json'))['version']
    removeTag(args.basedir,hassioAddonRepository, 'v' +version)
    githuburl = 'github:modbus2mqtt/server'
    replacements = [
        StringReplacement(pattern='version: v[0-9.][^\n]*', 
                          newValue='version: v' +  version + 
                          '\nimage: modbus2mqtt/modbus2mqtt-{arch}:' + version + 
                          '\ncodenotary: info@carcam360.de' ),
        StringReplacement(pattern='slug:.*', newValue='slug: modbus2mqtt'),
        ]
    replacementsDocker = [
        StringReplacement(pattern=githuburl+ '[^\n]*', newValue=githuburl + '#v' + version  )
        ]        
    updateConfigAndDockerfile(os.path.join(args.basedir, hassioAddonRepository,modbus2mqtt), version, replacements,replacementsDocker)
    print("TAG_NAME=v" + version)

