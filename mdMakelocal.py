import os, sys, re
import requests
import glob
import argparse
import uuid
import hashlib
import markdown
import mimetypes
import threading
import lxml.etree
import urllib.parse

class _Getch:
    """Gets a single character from standard input.  Does not echo to the
screen."""
    def __init__(self):
        try:
            self.impl = _GetchWindows()
        except ImportError:
            self.impl = _GetchUnix()
    def __call__(self): return self.impl()
class _GetchUnix:
    def __init__(self):
        import tty, sys
    def __call__(self):
        import sys, tty, termios
        fd = sys.stdin.fileno()
        old_settings = termios.tcgetattr(fd)
        try:
            tty.setraw(sys.stdin.fileno())
            ch = sys.stdin.read(1)
        finally:
            termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)
        return ch
class _GetchWindows:
    def __init__(self):
        import msvcrt
    def __call__(self):
        import msvcrt
        return msvcrt.getch()
getch = _Getch()

def getFilenameFromHeaders (headers, url):
    """ read the filetype from the header of a downloaded file using content-disposition, from content-type, or from the filename """
    # try to use the content-displisiton filename
    contentDisposition = headers.get('content-disposition')
    if contentDisposition:
        filenames = re.findall('filename=(.+)', contentDisposition)
        if type(filenames) is list:
            filename = filenames[0]
            filename = filename.strip("'").strip('"').strip()
            if filename:
                return filename
    
    # get filetype from headers
    fileExtension = mimetypes.guess_extension(headers['content-type'].partition(';')[0].strip())
    
    # try to use the url as filename
    urlPath = urllib.parse.urlparse(url)
    filename = os.path.basename(urlPath.path)  # Output: 09-09-201315-47-571378756077.jpg
    urlFileOnlyName, urlFileExtension = os.path.splitext(filename)
    # if filename contains an extension
    if urlFileExtension:
        if filename:
            return filename
    # no file extension in filename
    else:
        return filename + fileExtension
    
    # use a random id
    return uuid.uuid4() + fileExtension

def getUrlsInMarkdown(pMarkdownFilename):
    """ get a list of all urls referenced as <img> in a markdown file """
    urls = []
    with open(pMarkdownFilename, "r") as markdownFile:
        markdownFileContent = markdownFile.read()
        markdownFileAsMarkdown = bytes('<?xml version="1.0" encoding="utf8"?>\n<div>\n' + markdown.markdown(markdownFileContent) + '</div>\n', encoding='utf8')
        doc = lxml.etree.fromstring(markdownFileAsMarkdown)
        for link in doc.xpath('//img'):
            linkSrc = link.get('src')
            if (linkSrc.startswith('http')):
                urls.append(linkSrc)
    return urls


def replacemany(adict, astring):
    """ replace multiple keys with values from adic in astring """
    pat = '|'.join(re.escape(s) for s in adict)
    there = re.compile(pat)
    def onerepl(mo): return adict[mo.group()]
    return there.sub(onerepl, astring)


class Downloader(threading.Thread):
    """ threaded file downloading : generates filename, tries to prevent overwriting files by adding md5 sum to filename if file exists """
    def __init__(self, fileUrl, relativePath):
        super(Downloader, self).__init__()
        self.fileUrl = fileUrl
        self.relativePath = relativePath
        # by default leave the original path intact
        self.finalFilePath = self.fileUrl

    def run(self):
        # make sure the temp file path does not exist
        while True:
            uniqueId = str(uuid.uuid4())
            tempFilePath = os.path.join(self.relativePath, uniqueId)
            if (not os.path.exists(tempFilePath)):
                break

        print ("download %s as %s" % (self.fileUrl, tempFilePath))

        request = requests.get(self.fileUrl, stream = True)
        # https://stackoverflow.com/questions/14014854/python-on-the-fly-md5-as-one-reads-a-stream
        md5sig = hashlib.md5()
        with open(tempFilePath, 'wb') as file:
            for ch in request:
                md5sig.update(ch)
                file.write(ch)

        fileName = getFilenameFromHeaders(request.headers, self.fileUrl)
        fileTitle, fileExt = os.path.splitext(fileName)
        filePath = os.path.join(self.relativePath, fileName)

        # try to check if file is image to download
        try:
            fileMimetype = mimetypes.guess_type(fileName)[0]
            if (fileMimetype.split("/")[0] != "image"):
                print ("unknown mimetpe %s of file %s / %s : removing file" % (str(fileMimetype), self.fileUrl, filePath) )
                os.remove(tempFilePath)
                return
        except:
            print ("unable to guess mimetpe of %s / %s" % (self.fileUrl, filePath))
        
        # check if we need to rename the file because we the file has the same name, but a different file content
        if os.path.exists(filePath):
            # check if the existing file has the same md5sig
            existingMd5sig = hashlib.md5()
            with open(filePath, 'rb') as existingFile:
                for byte_block in iter(lambda: existingFile.read(4096),b""):
                    existingMd5sig.update(byte_block)
            
            if (existingMd5sig.hexdigest() == md5sig.hexdigest()):
                print ("md5sum of %s is equal, deleting downloaded file" % filePath)
            else:
                fileName = fileTitle + "_" + md5sig.hexdigest() + fileExt
                print ("existing file md5 %s differs from new file md5 %s" % (existingMd5sig.hexdigest(), md5sig.hexdigest()))
                print ("file '%s' already exists and md5 differs, using filename including md5sum as name '%s'" % (filePath, fileName))
                filePath = os.path.join(self.relativePath, fileName)

        if os.path.exists(filePath):
            print ("file '%s' already exists, using equal md5 sum, assuming file already downloaded" % filePath)
            os.remove(tempFilePath)
        else:
            print ("saving file as %s" % filePath)
            os.rename(tempFilePath, filePath)

        self.finalFilePath = filePath



if __name__ == "__main__":

    # if (len(sys.argv) < 2):
    #     print ("usage: python3 %s markdownFile.md ./MediaTargetFolder" % (sys.argv[0]))
    #     sys.exit()

    parser = argparse.ArgumentParser(
        description='Download linked images in Markdown File and generate new MD',
        usage='%(prog)s file.md [file2.md ..] [-m Folder]')
    # parser.add_argument('filename', type=str, nargs='+', help='markdown file[s]')
    parser.add_argument('path', nargs='+', help='Path of a file or a folder of files.')
    parser.add_argument("-m", "--media", help='specify folder for media downloads', required=False, default="./Media")
    args = parser.parse_args()

    # read list of markdown files
    full_paths = [os.path.normpath(os.path.join(os.getcwd(), path)) for path in args.path]
    markdownFiles = set()
    for path in full_paths:
        if os.path.isfile(path):
            markdownFiles.add(path)
        else:
            markdownFiles |= set(glob.glob(path + '/*' + '.md'))

    # read media folder
    mediaTargetFolder = args.media

    # check media folder exists
    if (not os.path.isdir(mediaTargetFolder)):
        print ("Media folder %s does not exist" % mediaTargetFolder)
        sys.exit()

    print ("detected markdown files")
    for filename in markdownFiles:
        print ("  %s" % filename)
    yna = ""
    while (yna not in ["y","n"]):
        print ("handle all these files? y(es) / n(o)")
        yna = getch().lower()
        if (yna == "n"):
            print ("aborted")
            sys.exit()

    # iterate all markdown files
    for markdownFilename in markdownFiles:
        print ("parsing %s" % markdownFilename)
        urlsInMarkDownFile = getUrlsInMarkdown(markdownFilename)
        if (len(urlsInMarkDownFile) == 0):
            print ("no downloadable urls found in %s" % markdownFilename)
        else:
            threads = []
            for i in range(len(urlsInMarkDownFile)):
                thread = Downloader(urlsInMarkDownFile[i], mediaTargetFolder)
                thread.start()
                threads.append(thread)
            
            replacements = {}
            for thread in threads:
                thread.join()
                # only if path has changed (othervise it has been skipped or deleted)
                if (thread.fileUrl != thread.finalFilePath):
                    print ("saved %s as %s"% (thread.fileUrl, thread.finalFilePath))
                    replacements[thread.fileUrl] = thread.finalFilePath

            # make sure we dont use a temp filename that already exists
            while True:
                markdownTempFilename = str(uuid.uuid4()) + ".md"
                if (not os.path.exists(markdownTempFilename)):
                    break
        
            print ("saving new temporary markdownfile with replaced links as %s" % markdownTempFilename)
            with open(markdownTempFilename, 'w') as fin:
                with open(markdownFilename, 'r') as ini:
                    fin.write(replacemany(replacements, ini.read()))
            
            markdownFileTitle, markdownFileExt = os.path.splitext(markdownFilename)
            # rename markdownTempFilename to markdownFilename-localMedia-X.md which does not exists
            newMarkdownFilename = "%s-localMedia.md" % markdownFileTitle
            newMarkdownFilenameIndex = 0
            while (os.path.exists(newMarkdownFilename)):
                newMarkdownFilenameIndex += 1
                newMarkdownFilename = "%s-localMedia-%i.md" % (markdownFileTitle, newMarkdownFilenameIndex)

            print ("rename temporary markdownfile %s as %s" % (markdownTempFilename, newMarkdownFilename))
            os.rename(markdownTempFilename, newMarkdownFilename)
