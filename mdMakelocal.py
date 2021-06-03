import os, sys, re
import requests
import uuid
import hashlib
import markdown
import mimetypes
import threading
import lxml.etree
import urllib.parse


''' read the filetype from the header of a downloaded file using content-disposition, from content-type, or from the filename '''
def getFilenameFromHeaders (headers, url):
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

''' get a list of all urls referenced as <img> in a markdown file '''
def getUrlsInMarkdown(pMarkdownFilename):
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


''' replace multiple keys with values from adic in astring '''
def replacemany(adict, astring):
    pat = '|'.join(re.escape(s) for s in adict)
    there = re.compile(pat)
    def onerepl(mo): return adict[mo.group()]
    return there.sub(onerepl, astring)


''' threaded file downloading : generates filename, tries to prevent overwriting files by adding md5 sum to filename if file exists '''
class Downloader(threading.Thread):
    def __init__(self, fileUrl, relativePath):
        super(Downloader, self).__init__()
        self.fileUrl = fileUrl
        self.relativePath = relativePath
        # by default leave the original path intact
        self.finalFilePath = self.fileUrl

    def run(self):
        uniqueId = str(uuid.uuid4())
        tempFilePath = os.path.join(self.relativePath, uniqueId)
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
        
        if os.path.exists(filePath):
            # check if the existing file has the same md5sig
            existingMd5sig = hashlib.md5()
            with open(filePath, 'rb') as existingFile:
                for byte_block in iter(lambda: existingFile.read(4096),b""):
                    existingMd5sig.update(byte_block)
            if (existingMd5sig.hexdigest() == md5sig.hexdigest()):
                print ("md5sum of %s is equal, overwriting file" % filePath)
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

    if (len(sys.argv) < 2):
        print ("usage: python3 %s markdownFile.md ./MediaTargetFolder" % (sys.argv[0]))
        sys.exit()

    markdownFilename = sys.argv[1]
    mediaTargetFolder = sys.argv[2]
    markdownTempFilename = str(uuid.uuid4()) + ".md"

    if (not os.path.exists(markdownFilename)):
        print ("markdownFilename %s does not exist" % markdownFilename)
        sys.exit()

    if (not os.path.isdir(mediaTargetFolder)):
        print ("MediaTargetFolder %s does not exist" % mediaTargetFolder)
        sys.exit()

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
