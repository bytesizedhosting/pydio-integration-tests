# -*- coding: utf-8 -*-
#  Copyright (©) 2016 Thomas Saliou - Abstrium SAS <team (at) pydio.com>
#
#  This program is free software; you can redistribute it and/or
#  modify it under the terms of the GNU General Public License
#  as published by the Free Software Foundation; version 2 of the License.
#
#  This program is distributed in the hope that it will be useful,
#  but WITHOUT ANY WARRANTY; without even the implied warranty of
#  MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#  GNU General Public License for more details.
#
#  You should have received a copy of the GNU General Public License
#  along with Pydio.  If not, see <http://www.gnu.org/licenses/>.
#

import argparse, json, time, os, unicodedata
import humanize, getpass, fnmatch
from test import manyfilestest, manyimagestest, randname, Bot
from watchdog.utils.dirsnapshot import DirectorySnapshot as dirsnap
import platform

import sys
sys.path.append('..')
from sdk.remote import PydioSdk
from sdk.exceptions import PydioSdkBasicAuthException

# Python 3
if sys.version_info[0] < 3:
    print("Sorry this requires Python 3+")
    exit(-1)

def toset(prefix, pathset):
    """ transform an absolute path set to a relative path set """
    rel_path = set()
    for p in pathset:
        rel_path.add(p.replace(prefix, ''))
    return rel_path

def docheck(sdk, path, subfolder=""):
    """ Using PydioSdk connects to a server and compares the list of files at
        :param path: with the list of files at the :param sdk:
    """
    remote_ls = sdk.list(recursive='true')
    if subfolder != "":
        remote2 = {}
        for p in remote_ls:
            remote2[p.replace(subfolder, "", 1)] = remote_ls[p]
        remote_ls = remote2
    local_ls = dirsnap(path)
    def dodiff(remotefiles, localfiles):
        """ from {'path/to/file': file, ...}, set('path/to/file', ...) do a
            check that the same files are present returns dict of dict of files
            {missing_local, missing_remote}
        """
        missing = {}
        for k in remotefiles.keys():
            try:
                if platform.system() == 'Darwin':
                    localfiles.remove(unicodedata.normalize('NFD', k))
                else:
                    localfiles.remove(os.path.normpath(k))
            except KeyError as e:
                missing[k] = time.time()
        return {"missing_local" : missing, "missing_remote": localfiles}
    #print(remote_ls)
    diff = dodiff(remote_ls, toset(path, local_ls.paths))
    return diff

def parseWithExcludes(diff, excludes):
    """ Parses a diff, returns only items not matching excludes
        :param diff: will be MUTATED
        :param excludes: the list of patterns to delete
        TODO This code could probably be heavily optimized if the need appeared
    """
    ndiff = {"missing_remote": set(), "missing_local": dict()}
    excludes.append('')
    for p in diff["missing_local"].keys():
        skip = False
        for patt in excludes:
            if fnmatch.fnmatch(p, patt):
                skip = True
                break
        if not skip:
            ndiff["missing_local"][p] = diff["missing_local"][p]
    for p in diff["missing_remote"]:
        skip = False
        for patt in excludes:
            if fnmatch.fnmatch(p, patt):
                skip = True
                break
        if not skip:
            ndiff["missing_remote"].add(p)
    return ndiff

def dofullcheck(conf):
    sdk = PydioSdk(conf[args.job]['server'], conf[args.job]['workspace'], conf[args.job]['remote_folder'], '',
        auth=(conf[args.job]['user'], PASSWORD),
        skip_ssl_verify=True)  # FIXME: only for development
    excludes = conf[args.job]['filters']['excludes']
    diff = docheck(sdk, conf[args.job]['directory'], conf[args.job]['remote_folder'])
    cleaned = parseWithExcludes(diff, excludes)
    print(cleaned)
    if len(cleaned["missing_local"]) == len(cleaned["missing_remote"]) == 0:
        print("Synchronised ✔")
    else:
        print("Files to download " + str(len(cleaned["missing_local"])) + ". Files to upload " + str(len(cleaned["missing_remote"])))

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    if platform.system() == 'Windows':
        parser.add_argument('--config', help="A configs.json file to be loaded", default=os.getenv('APPDATA') + "//Pydio//configs.json")
    else:
        parser.add_argument('--config', help="A configs.json file to be loaded", default="/Users/" + os.getlogin() + "/Library/Application Support/Pydio/configs.json")
    parser.add_argument('--job', help="The job to use to create some files", default="my-files")
    parser.add_argument('--noconfirm', help="Proceed without confirmation", type=bool, default=False)
    parser.add_argument('--nbfiles', help="Number of files to create", default=50, type=int)
    parser.add_argument('--onlypics', help="Only create pictures", type=bool, default=True)
    parser.add_argument('--password', '-p', help="Your Pydio ASCII password (risky), use -p '' to get a prompt", default='pydiopassword')
    parser.add_argument('--check', help="This mode is used to check a workspace id. Creates a local snapshot and compares it to a distant sync.", type=bool, default=False)
    parser.add_argument('--synctest', help="Do a sync test, - BEWARE DELETES FILES -. An integer value can specify a delay in second between every action", default=0, type=int)
    parser.add_argument('--filetest', help="Creates some files, (todo optional delay between creation)", default=0)
    args = parser.parse_args()

    print("Loading config... " + args.config)
    conf_handler = open(args.config)
    conf = json.load(conf_handler)
    # Setting parameters
    NBFILES = args.nbfiles
    if args.job in conf:
        FLD = conf[args.job]["directory"]
        # prompt for password if needed
        if args.password == '':
            PASSWORD = getpass.getpass('Password:')
        else:
            PASSWORD = args.password

        #### MODES ####
        # Checks that a folder is properly synchronized
        if args.check:
            dofullcheck(conf)
        if args.synctest > 0:
            b = Bot(conf[args.job]["directory"])
            try:
                waittime = int(args.synctest)
                b.dosomethings(args.nbfiles, waittime)
                print(b)
            except ValueError:  # if the arg wasn't an int
                b.dosomethings(args.nbfiles, 1)
            while True:
                try:
                    leinput = input('[c]heck|[M]ore|[q]uit >')
                    if leinput == '' or leinput[0].lower() == 'm':
                        print(b.dosomething())
                    elif leinput[0].lower() == 'c':
                        try:
                            dofullcheck(conf)
                        except PydioSdkBasicAuthException:
                            print("Auth failed")
                            PASSWORD = getpass.getpass('Password:')
                    elif leinput[0] == 'q':
                        break
                except KeyboardInterrupt:
                    pass
            print("--- Things done ---")
            print(b)
            with open('test_interactive.log', 'w') as log:
                log.write(str(b))

        if args.filetest > 0:
            # Create some files
            if not args.noconfirm:
                confirm = input("Will create " + str(args.nbfiles) + " images in " + FLD + " (y/n) \n >")
                args.noconfirm = (confirm[0].lower() == 'y')
            if args.noconfirm:
                dest = FLD+"/"+randname(8)
                start = time.time()
                size = 0
                if not args.onlypics:
                    size = manyfilestest(NBFILES/2, FLD)
                size += manyimagestest(NBFILES, dest)
                finish = time.time()
                print("Done, created " + humanize.naturalsize(size) + " in " + humanize.naturaltime(finish-start)[:-4] + ". In folder file://" + dest)
            else:
                print("Aborted. No files created. --noconfirm True?")
            # Wait for files to be synced
            # Create a new sync task
            # Wait for download to be done
            # Check Syncs contents'
    else:
        print("Not enough information to proceed..." + "\n \033[92m Example usage: \
                \n\tpython test_interactive.py --job name_of_job --synctest 2 --nbfiles 100 \
                \n\tpython test_interactive.py --job name_of_job --check True\033[37m")
        print("List of available jobs:")
        for i in conf:
            print(" " + i + " -> (" + conf[i]["directory"] + ")")
        parser.print_help()
