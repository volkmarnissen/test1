#!/usr/bin/env python3
import argparse
import repositories

parser = argparse.ArgumentParser()
parser.add_argument("repositorys", help="repositories.json file ",  type=str)

args = parser.parse_args()
repositorysList = repositories.readrepositorys(args.repositorys)
repositories.doWithRepositorys('test')