"""Main module."""
import hashlib
import os
import glob
from configparser import ConfigParser
import urllib.parse

from notion.block import PageBlock
from notion.block import TextBlock
from notion.client import NotionClient
from md2notion.upload import upload


TOKEN = os.getenv("NOTION_TOKEN_V2", "")
_client = None


def get_client():
    global _client
    if not _client:
        _client = NotionClient(token_v2=TOKEN)
    return _client


def get_or_create_page(base_page, title):
    page = None
    for child in base_page.children.filter(PageBlock):
        if child.title == title:
            page = child

    if not page:
        page = base_page.children.add_new(PageBlock, title=title)
    return page


def upload_file(base_page, filename: str, page_title=None):
    # Extract the first line from the file to use as a title if page_title is not provided
    if not page_title:
        with open(filename, "r", encoding="utf-8") as mdFile:
            first_line = mdFile.readline().strip()
            # Assuming the first line is a Markdown header, we remove the '#' characters
            first_line = first_line.lstrip('#').strip()

    # Extracting the last folder name from the path
    last_folder_name = os.path.basename(os.path.dirname(filename))
    if last_folder_name:
        page_title = f"{last_folder_name} - {first_line}"
    else:
        page_title = first_line

    github_root = os.getenv("GITHUB_REPO_ROOT", "https://github.com/rb2-bv/core-connect/blob/main/") # Default if env var is not set
    encoded_filename = urllib.parse.quote(filename)
    file_url = os.path.join(github_root, encoded_filename)
    markdown_link = f"[{filename}]({file_url})"

    page = get_or_create_page(base_page, page_title)
    hasher = hashlib.md5()
    with open(filename, "rb") as mdFile:
        buf = mdFile.read()
        hasher.update(buf)
    if page.children and hasher.hexdigest() in str(page.children[0]):
        return page

    for child in page.children:
        child.remove()

    # Add MD5 hash and file URL to the page
    page.children.add_new(TextBlock, title=f"MD5: {hasher.hexdigest()}")
    page.children.add_new(TextBlock, title="File URL: {}".format(markdown_link))

    with open(filename, "r", encoding="utf-8") as mdFile:
        upload(mdFile, page)
    return page


def sync_to_notion(repo_root: str = "."):
    os.chdir(repo_root)
    config = ConfigParser()
    config.read(os.path.join(repo_root, "setup.cfg"))
    repo_name = os.path.basename(os.getcwd())

    root_page_url = os.getenv("NOTION_ROOT_PAGE") or config.get('git-notion', 'notion_root_page')
    
    # Get the ignore directories from the environment variable or config file
    ignore_dirs_str = os.getenv("NOTION_IGNORE_DIRS") or config.get('git-notion', 'ignore_dirs', fallback="")
    ignore_dirs = ignore_dirs_str.split(',') if ignore_dirs_str else []

    root_page = get_client().get_block(root_page_url)
    repo_page = get_or_create_page(root_page, repo_name)

    # Combining results from both regular and hidden directories
    all_md_files = glob.glob('**/*.md', recursive=True)
    hidden_md_files = glob.glob('**/.*/*.md', recursive=True)
    combined_md_files = all_md_files + hidden_md_files

    for file in combined_md_files:
        if not any(dir in file for dir in ignore_dirs):
            print(file)
            upload_file(repo_page, file)
