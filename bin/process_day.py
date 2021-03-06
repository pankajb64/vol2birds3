#!/usr/bin/python
import sys
import boto
import os
import shutil
import gzip
import tempfile
import radcp
import getopt
from subprocess import call
from shutil import copyfile
from boto.s3.key import Key

def main(argv):
   me = sys.argv[0] 

   if len(argv) == 0:
      # no input arguments, check whether an ARGS environment variable is set
      if not "ARGS" in os.environ:
         print >> sys.stderr, "No input arguments and environment variable 'ARGS' not found, aborting"
         sys.exit()

      # get the contents of the ARGS environment variable
      args = os.environ["ARGS"]
      print "executing",me,args
      argslist=args.split()
   else:
      argslist = argv

   radar=''
   date = ''
   night = False
   step = 5
   zipQ = False
   aws = False
   docker = False

   try:
      opts, args = getopt.getopt(argslist,"hangr:d:s:",["help","aws","night","gzip","radar=","date=","step="])
   except getopt.GetoptError:
      print "error: unrecognised arguments"
      print me+' -r <radar> -d <date> [--night] [--gzip] [--step <mins>] [--aws]'
      print me+' -h | --help'
      sys.exit(2)
   for opt, arg in opts:
      if opt in ('-h', "--help"):
         print 'Usage: '
         print '  '+me+' -r <radar> -d <date> [--night] [--gzip] [--step <mins>] [--aws]'
         print '  '+me+' -h | --help'
         print '\nOptions:'
         print '  -h --help     Show this screen'
         print '  -r --radar    Specify NEXRAD radar, e.g. KBGM'
         print '  -g --gzip     Compress output'
         print '  -d --date     Specify date in yyyy/mm/dd format'
         print '  -n --night    If set, only download nighttime data'
         print '  -s --step     Minimum timestep in minutes between consecutive polar volumes [default: 5]'
         print '  -a --aws      Store output in vol2bird bucket on aws'
         sys.exit()
      elif opt in ("-n", "--night"):
         night = True
      elif opt in ("-a", "--aws"):
         aws = True
      elif opt in ("-g", "--gzip"):
         zipQ = True
      elif opt in ("-d", "--date"):
         date = arg
      elif opt in ("-r", "--radar"):
         radar = arg
      elif opt in ("-s", "--step"):
         step = float(arg)
   if not(radar != '' and date != ''):
      print "error: both a radar and date specification required"
      print me+' -r <radar> -d <date> [--night] [--gzip] [--step <mins>] [--aws]'
      print me+' -h | --help'
      sys.exit()

   # check whether we are inside a Docker container
   fcgroup="/proc/1/cgroup"
   if os.path.exists(fcgroup):
      with open(fcgroup, "r") as cgroupfile:
         if "docker" in cgroupfile.read():
             docker=True

   # store the current working directory
   cwd = os.getcwd()

   # make a temporary directory to store the radar data to be downloaded
   tmppath=tempfile.mkdtemp()
   # change the working directory to the new temporary directory
   os.chdir(tmppath)

   # copy the radar files, using radcp with arguments split as a list
   # keep only the radcp arguements
   argscp=argslist
   if '--gzip' in argscp:
      argscp.remove('--gzip')
   if '-g' in argscp:
      argscp.remove('-a')
   if '--aws' in argscp:
      argscp.remove('--aws')
   if '-a' in argscp:
      argscp.remove('-a')
   radcp.main(argscp)

   # count the number of files
   NFile = len(os.listdir(tmppath))
   if NFile == 0:
      print >> sys.stderr, 'no files found'
      shutil.rmtree(tmppath)
      sys.exit()

   # get the file list of polar volumes to be processed
   pvols = sorted(os.listdir(tmppath))

   # write an option file if OPTS environment variable is set
   # should contain option.conf statements separated by \n
   if "OPTS" in os.environ:
      optsfile = open("options.conf", "w")
      opts = os.environ["OPTS"].replace('\\n', '\n')
      optsfile.write(opts)
      optsfile.close()

   # construct output filename from input argument string
   fout=radar+date+".txt"
   fout=fout.replace('/','')

   with open(fout, "a") as myfile:
      for pvol in pvols:
         localfile = os.path.basename(pvol)
         # process the volume file with vol2bird, write to myfile
         call(["vol2bird",localfile],stdout=myfile)
      myfile.close()
      # compress myfile and copy it to original working directory
      if zipQ:
         with open(fout, "r") as myfile:
            with gzip.open(fout + ".gz", 'wb') as zipfile:
               shutil.copyfileobj(myfile, zipfile)
               zipfile.close()
               # include gz extension to the output file
               fout=fout+".gz"
            myfile.close()


   # upload the output to s3
   if aws:
      conn = boto.connect_s3()
      bucket = conn.get_bucket('vol2bird')
      k = Key(bucket)
      k.key = radar+"/"+date+"/"+fout 
      k.set_contents_from_filename(fout)
   else:
      if docker:
         copyfile(fout,'/data/'+fout)
      else:
         copyfile(fout,cwd+'/'+fout)

   # clean up 
   shutil.rmtree(tmppath)

if __name__ == "__main__":
   main(sys.argv[1:])
