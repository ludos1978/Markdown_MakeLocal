# Markdown_MakeLocal
Analyze a Markdown file for Image URLs, download these files and generate a new markdown with the downloaded files.

Has only been tested on OSX!

## Usage
> python3 ./mdMakelocal.py markdownfile.md ./MediaFolder

## Requirements
- python3

with the libraries
- requests
- uuid
- hashlib
- markdown
- mimetypes
- threading
- lxml.etree
- urllib.parse

## Things Considered in Development
- If the filename already exists in the media folder, it will append the files md5 hash to the filename
- The original markdown file will no be modified, only a new one generated with the appendix '-localMedia-X' where X is a number increased when a file already exists with that name.
- Downloads are threaded
- Image Filename and extension is generated from (in the following order)
    - html header 'content-disposition'
    - filename and html header 'content-type'
    - filename itself

## Known Problems / Kwirks
- All links are downloaded, only afterwards the mimetype is detected. Then the file will be deleted if it's not matching a image type.
- the generated filename could be to long for the filesystem.
- Markdown file is converted to html to check for links, maybe would be nicer with regex? 

## Example Links to Images
Image links from w3.org to test the script on this file

> BMP
![](https://www.w3.org/People/mimasa/test/imgformat/img/w3c_home.bmp)

> GIF
![](https://www.w3.org/People/mimasa/test/imgformat/img/w3c_home.gif)

> JPG
![](https://www.w3.org/People/mimasa/test/imgformat/img/w3c_home.jpg)

> PNG
![](https://www.w3.org/People/mimasa/test/imgformat/img/w3c_home.png)
