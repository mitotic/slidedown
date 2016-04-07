#!/usr/bin/env python

'''
Filter Markdown files.

'''

from __future__ import print_function

import base64
import os
import random
import re
import sys
import urllib
import urllib2
import urlparse

from collections import defaultdict, namedtuple, OrderedDict

import mistune

def read_file(path):
    with open(path) as f:
        return f.read()
    
def write_file(path, *args):
    with open(path, 'w') as f:
        for arg in args:
            f.write(arg)
    
def ref_key(text):
    # create reference key: compress multiple spaces, and lower-case
    return re.sub(r'\s+', ' ', text).strip().lower()

def make_id_from_text(text):
    """Make safe ID string from string"""
    return urllib.quote(re.sub(r'[^-\w\.]+', '-', text.lower().strip()).strip('-').strip('.'), safe='')

def generate_random_label(id_str=''):
    if id_str:
        return '%04d-%s' % (random.randint(0, 9999), id_str)
    else:
        return '%03d-%04d' % (random.randint(0, 999), random.randint(0, 9999))

def get_url_scheme(url):
    match = re.match(r'^([-a-z]{3,5}):\S*$', url)
    if match:
        return match.group(1)
    return 'abs_path' if url.startswith('/') else 'rel_path'

def quote_pad_title(title, parentheses=False):
    # Quote non-null title and pad left
    if not title:
        return title
    if '"' not in title:
        return ' "'+title+'"'
    elif "'" not in title:
        return " '"+title+"'"
    elif parentheses and '(' not in title and ')' not in title:
        return " ("+title+")"
    return ''

class Parser(object):
    newline_norm_re =  re.compile( r'\r\n|\r')
    indent_strip_re =  re.compile( r'^ {4}', re.MULTILINE)
    annotation_re =    re.compile( r'^Annotation:')
    answer_re =        re.compile( r'^(Answer|Ans):')
    concepts_re =      re.compile( r'^Concepts:')
    inline_math_re =   re.compile(r"^`\$(.+?)\$`")
    notes_re =         re.compile( r'^Notes:')
    ref_re =           re.compile(r'''^ {0,3}\[([^\]]+)\]: +(\S+)( *\(.*\)| *'.*'| *".*")? *$''')
    ref_def_re =  re.compile(r'''(^|\n) {0,3}\[([^\]]+)\]: +(\S+)( *\(.*\)| *'.*'| *".*")? *(\n+|$)''')

    rules_re = [ ('fenced',            re.compile( r'^ *(`{3,}|~{3,}) *(\S+)? *\n'
                                                   r'([\s\S]+?)\s*'
                                                   r'\1 *(?:\n+|$)' ) ),
                 ('indented',          re.compile( r'^( {4}[^\n]+\n*)+') ),
                 ('block_math',        re.compile( r'^\$\$(.*?)\$\$', re.DOTALL) ),
                 ('latex_environment', re.compile( r'^\\begin\{([a-z]*\*?)\}(.*?)\\end\{\1\}',
                                                   re.DOTALL) ),
                 ('hrule',      re.compile( r'^([-]{3,}) *(?:\n+|$)') ),
                 ('minirule',   re.compile( r'^(--) *(?:\n+|$)') )
                  ]

    link_re = re.compile(
        r'!?\[('
        r'(?:\[[^^\]]*\]|[^\[\]]|\](?=[^\[]*\]))*'
        r')\]\('
        r'''\s*(<)?([\s\S]*?)(?(2)>)(?:\s+['"]([\s\S]*?)['"])?\s*'''
        r'\)'
    )

    reflink_re = re.compile(
        r'!?\[('
        r'(?:\[[^^\]]*\]|[^\[\]]|\](?=[^\[]*\]))*'
        r')\]\s*\[([^^\]]*)\]'
    )

    url_re = re.compile(r'''^(https?:\/\/[^\s<]+[^<.,:;"')\]\s])''')
    data_url_re = re.compile(r'^data:([^;]+/[^;]+);base64,(.*)$')

    img_re = re.compile(r'''<img(\s+\w+(=[^'"\s]+|='[^'\n]*'|="[^"\n]*")?)*\s*>''')
    attr_re_format = r'''\s%s=([^'"\s]+|'[^'\n]*'|"[^"\n]*")'''

    slidoc_choice_re = re.compile(r"^ {0,3}([a-pA-P])\.\. +")
    header_attr_re = re.compile(r'^(\s*#+.*?)(\s*\{\s*#([-.\w]+)(\s+[^\}]*)?\s*\})\s*$')
    internal_ref_re =  re.compile(
        r'\[('
        r'(?:\[[^^\]]*\]|[^\[\]]|\](?=[^\[]*\]))*'
        r')\]\s*\{\s*#([^^\}]*)\}'
    )
    
    def __init__(self, cmd_args):
        self.cmd_args = cmd_args
        self.arg_check(cmd_args)
        self.skipping_notes = False
        self.cells_buffer = []
        self.buffered_markdown = []
        self.output = []
        self.imported_links = {}
        self.imported_defs = OrderedDict()
        self.imported_refs = OrderedDict()
        self.exported_refs = OrderedDict()
        self.image_refs = {}
        self.old_defs = OrderedDict()
        self.new_defs = OrderedDict()
        self.filedir = ''

    def arg_check(self, arg_set):
        n = 0
        for opt in ('check', 'copy', 'import', 'export'):
            if hasattr(arg_set, opt):
                n += 1
        if n > 1:
            sys.exit('ERROR Only one of check|copy|import|export may be specified for --images')

    def write_content(self, filepath, content, dry_run=False):
        """Write content to file. If file already exists, check its content"""
        fdir = os.path.dirname(filepath)
        if fdir and not os.path.exists(fdir):
            os.mkdir(fdir)
        elif os.path.exists(filepath):
            if content == read_file(filepath):
                return
            if not self.cmd_args.overwrite:
                raise Exception('Error: Specify --overwrite to copy %s' % filepath)
        if not dry_run:
            write_file(filepath, content)

    def get_link_data(self, link, check_only=False, data_url=False):
        ''' Returns (filename, content_type, content)
            content is data URL if data_url, else raw data.
            Returns None for filename on error
        '''
        try:
            filename = ''
            content_type = ''
            content = ''
            url_type = get_url_scheme(link)
            if url_type == 'data':
                # Data URL
                match = self.data_url_re.match(link)
                if not match:
                    raise Exception('Invalid data URL')
                content_type = match.group(1)
                if data_url:
                    content = link
                else:
                    content = base64.b64decode(match.group(2))

            elif url_type.startswith('http'):
                # HTTP URL
                filename = os.path.basename(urlparse.urlsplit(link).path.rstrip('/'))
                request = urllib2.Request(link)
                if check_only:
                    request.get_method = lambda : 'HEAD'
                response = urllib2.urlopen(request)
                content_type = response.info().getheader('Content-Type')
                if not check_only:
                    content = response.read()
                    if data_url:
                        content = ('data:%s;base64,' % content_type) +  base64.b64encode(content)

            elif url_type == 'rel_path':
                # Relative file "URL"
                filename = os.path.basename(link)
                filepath = self.filedir+'/'+link
                if not os.path.exists(filepath):
                    raise Exception('File %s does not exist' % filepath)

                if not check_only:
                    _, extn = os.path.splitext(os.path.basename(filepath))
                    extn = extn.lower()
                    if extn in ('.gif', '.jpg', '.jpeg', '.png', '.svg'):
                        content_type = 'image/jpeg' if extn == '.jpg' else 'image/'+extn[1:]

                    content = read_file(filepath)
                    if data_url:
                        if not content_type:
                            raise Exception('Unknown content type for file %s' % filename)
                        content = ('data:%s;base64,' % content_type) +  base64.b64encode(content)
            else:
                # Other URL type
                pass

            return filename, content_type, content
        except Exception, excp:
            print('ERROR in retrieving link %s: %s' % (link, excp), file=sys.stderr)
            return None, '', ''

    def external_link(self, match):
        orig_content = match.group(0)
        text = match.group(1)
        link = match.group(3)
        title = match.group(4) or ''

        is_image = orig_content.startswith('!')
        if not is_image:
            if link.startswith('#'):
                if link == '#' or link == '##':
                    link += text.strip()
                if 'pandoc' in self.cmd_args.images:
                    if link.startswith('##'):
                        return text+'(number)'
                    return '[%s](%s%s)' % (text, link, quote_pad_title(title))
            return orig_content

        if title and 'pandoc' in self.cmd_args.images:
            attrs = []
            for attr in ('height', 'width'):
                value = self.get_html_tag_attr(attr, ' '+title)
                if value:
                    attrs.append(attr + '=' + value)
            if attrs:
                return orig_content + ' { ' + ' '.join(attrs) + ' }'
            else:
                return orig_content

        url_type = get_url_scheme(link)

        if url_type == 'rel_path' or (url_type.startswith('http') and 'web' in self.cmd_args.images):
            if 'import' in self.cmd_args.images:
                # Check if link has already been imported (with the same title)
                    if 'embed' in self.cmd_args.images:
                        filename, new_title, new_link = self.import_link(link, title)
                        if filename is not None:
                            return self.make_img_tag(new_link, text, new_title)
                    else:
                        key, new_title, new_link = self.import_ref(link, title)
                        if key:
                            return '![%s][%s]' % (text, key)

            elif 'check' in self.cmd_args.images:
                self.copy_image(text, link, title, check_only=True)

            elif 'copy' in self.cmd_args.images:
                new_link, new_title = self.copy_image(text, link, title)
                if new_link is not None:
                    if 'embed' in self.cmd_args.images:
                        return self.make_img_tag(new_link, text, new_title)
                    return '![%s](%s%s)' % (text, new_link, quote_pad_title(new_title))

        if 'embed' in self.cmd_args.images:
            # Convert ref to embedded image tag
            return self.make_img_tag(link, text, title)

        return orig_content

    def copy_image(self, text, link, title, check_only=False):
        """Copies image file to destination. Returns (new_link, title) or (None, None) (for copied URLs)"""
        filename, content_type, content = self.get_link_data(link, check_only=check_only, data_url=False)

        if filename is None:
            print('ERROR: Unable to retrieve image %s' % link, file=sys.stderr)
        elif not check_only and not content:
            print('ERROR: No data in image file %s' % link, file=sys.stderr)
        elif content_type and not content_type.startswith('image/'):
            print('ERROR: Link %s does not contain image data (%s)' % (link, content_type), file=sys.stderr)

        elif not check_only:
            url_type = get_url_scheme(link)
            new_link = ''
            if url_type.startswith('http'):
                _, extn = content_type.split('/')
                newpath = os.path.basename(urlparse.urlsplit(link).path.rstrip('/'))
                if not newpath.endswith('.'+extn):
                    newpath += '.'+extn
                if self.cmd_args.image_dir:
                    newpath = self.cmd_args.image_dir + '/' + newpath
                new_link = newpath

            elif url_type == 'rel_path':
                if 'gather_images' in self.cmd_args.images:
                    # Copy all images to new destination image directory
                    newpath = os.path.basename(link)
                    if self.cmd_args.image_dir:
                        newpath = self.cmd_args.image_dir + '/' + newpath
                    if newpath != link:
                        new_link = newpath
                else:
                    # Preserve relative path when copying
                    newpath = link

            if self.cmd_args.dest_dir:
                newpath = self.cmd_args.dest_dir + '/' + newpath

            try:
                self.write_content(newpath, content)

                print('Copied link %s to %s' % (link, newpath), file=sys.stderr)
                if new_link:
                    # Convert URL to local file link
                    return new_link, title
            except Exception, excp:
                print('ERROR in copying link %s to %s: %s' % (link, newpath, excp), file=sys.stderr)

        return None, None

    def ref_link(self, match):
        # Internal reference
        orig_content = match.group(0)
        text = match.group(1)
        if len(match.groups()) < 2:
            key = ref_key(text)
        else:
            key = ref_key(match.group(2) or match.group(1))

        if not orig_content.startswith("!"):
            # Not image
            if not key.startswith('#'):
                return orig_content
            if key == '#' or key == '##':
                key += text.strip()
            if 'pandoc' in self.cmd_args.images:
                if key.startswith('##'):
                    return text+'(number)'
                return text
            else:
                return orig_content

        self.image_refs[key] = text

        if 'embed' in self.cmd_args.images:
            # Convert ref to embedded image tag
            if key in self.new_defs:
                link, title = self.new_defs[key]
                return self.make_img_tag(link, text, title)
            elif key in self.old_defs:
                link, title = self.old_defs[key]
                return self.make_img_tag(link, text, title)

        if 'export' in self.cmd_args.images:
            # Convert exported refs to external links
            if key in self.new_defs:
                link, title = self.new_defs[key]
                return '![%s](%s%s)' % (text, link, quote_pad_title(title))

        return orig_content

    
    def make_img_tag(self, src, alt, title):
        '''Return img tag string, supporting extension of including align/height/width attributes in title string'''
        attrs = ''
        if title:
            for attr in ('align', 'height', 'width'):
                value = self.get_html_tag_attr(attr, ' '+title)
                if value:
                    attrs += ' ' + attr + '=' + value
            attrs += ' title="' + mistune.escape(title, quote=True) + '"'

        if get_url_scheme(src) == 'rel_path' and self.cmd_args.image_url:
            src = self.cmd_args.image_url + src
            
        return '<img src="%s" alt="%s" %s>' % (src, alt, attrs)

    def get_html_tag_attr(self, attr_name, tag_text):
        match = re.search(self.attr_re_format % attr_name, tag_text)
        return match.group(1).strip('"').strip("'") if match else ''

    def img_tag(self, match):
        orig_content = match.group(0)

        src = self.get_html_tag_attr('src', orig_content)
        if not src:
            return orig_content
        url_type = get_url_scheme(src)

        if 'check' in self.cmd_args.images:
            if url_type == 'rel_path' or (url_type.startswith('http') and 'web' in self.cmd_args.images):
                filename, content_type, content = self.get_link_data(src, check_only=True)
                if filename is None:
                    print('ERROR: Unable to retrieve image %s' % src, file=sys.stderr)

        if self.cmd_args.image_url:
            if url_type == 'rel_path':
                new_src = self.cmd_args.image_url + src
                return orig_content.replace(src, new_src)

        elif url_type == 'rel_path' or (url_type.startswith('http') and 'web' in self.cmd_args.images):
            if 'import' in self.cmd_args.images and 'embed' in self.cmd_args.images:
                # Check if link has already been imported (with the same title); if not import it
                filename, new_title, new_link = self.import_link(src, '')
                if filename is not None:
                    return orig_content.replace(src, new_link)   # Data URL
                    
        return orig_content

    def parse(self, content, filepath=''):
        if filepath:
            self.filedir = os.path.dirname(os.path.realpath(filepath))

        content = self.newline_norm_re.sub('\n', content) # Normalize newlines

        if self.cmd_args.images:
            # Parse all ref definitions first
            for match in self.ref_def_re.finditer(content):
                key = ref_key(match.group(2))
                link = match.group(3)
                title = match.group(4)[2:-1] if match.group(4) else ''

                self.old_defs[key] = (link, title)
                url_type = get_url_scheme(link)
                if 'export' in self.cmd_args.images and url_type == 'data':
                    # Export ref definition
                    _, new_link, new_title = self.export_ref_definition(key, link, title)
                    if new_link:
                        self.new_defs[key] = (new_link, new_title)
                        self.exported_refs[key] = new_link
                elif 'import' in self.cmd_args.images and not url_type != 'data':
                    if url_type == 'rel_path' or (url_type.startswith('http') and 'web' in self.cmd_args.images):
                        # Relative file "URL" or web URL (with web enabled)
                        _, new_title, new_link = self.import_ref(link, title, key=key)
        
        while content:
            matched = None
            for rule_name, rule_re in self.rules_re:
                # Find the first match
                matched = rule_re.match(content)
                if matched:
                    break

            if matched:
                self.process_buffer()

                # Strip out matched text
                content = content[len(matched.group(0)):]

                if rule_name == 'fenced':
                    if 'code' not in self.cmd_args.strip:
                        if self.cmd_args.unfence:
                            self.output.append( re.sub(r'(^|\n)(.)', '\g<1>    \g<2>', matched.group(3))+'\n\n' )
                        else:
                            self.output.append(matched.group(0))

                elif rule_name == 'indented':
                    if self.cmd_args.fence:
                        fenced_code = "```\n" + re.sub(r'(^|\n) {4}', '\g<1>', matched.group(0)) + "```\n\n"
                        self.output.append(fenced_code)
                    else:
                        self.output.append(matched.group(0))

                elif rule_name == 'block_math':
                    self.math_block(matched.group(0))

                elif rule_name == 'latex_environment':
                    self.math_block(matched.group(0), latex=True)

                elif rule_name == 'hrule':
                    self.hrule(matched.group(1))

                elif rule_name == 'minirule':
                    self.minirule(matched.group(1))
                else:
                    raise Exception('Unknown rule: '+rule_name)

            elif '\n' in content:
                # Process next line
                line, _, content = content.partition('\n')
                if self.skipping_notes:
                    pass
                elif self.annotation_re.match(line) and not self.cmd_args.keep_annotation:
                    pass
                elif self.answer_re.match(line) and 'answers' in self.cmd_args.strip:
                    pass
                elif self.concepts_re.match(line) and 'concepts' in self.cmd_args.strip:
                    pass
                elif self.notes_re.match(line) and 'notes' in self.cmd_args.strip:
                    self.skipping_notes = True
                else:
                    match_ref = self.ref_re.match(line)
                    if match_ref:
                        # Ref def line; process markdown in buffer
                        self.process_buffer()
                        key = ref_key(match_ref.group(1))
                        if key in self.image_refs and 'embed' in self.cmd_args.images:
                            # Embedding image refs; skip definition
                            pass
                        elif key in self.new_defs:
                            # New ref def
                            new_link, new_title = self.new_defs[key]
                            self.buffered_markdown.append('[%s]: %s%s\n' % (key, new_link, quote_pad_title(new_title,parentheses=True)) )
                        else:
                            # Old ref def
                            self.buffered_markdown.append(line+'\n')
                    else:
                        # Normal markdown line
                        if 'extensions' in self.cmd_args.strip:
                            if self.slidoc_choice_re.match(line):
                                # Strip slidoc extension for interactive multiple-choice
                                line = re.sub('\.\.', '.', line, count=1)
                            if 'pandoc' not in self.cmd_args.images:
                                # Strip slidoc extension for header attributes (Only the # case)
                                line = self.header_attr_re.sub(r'\1', line)
                            # Strip slidoc extension for internal references
                            line = self.internal_ref_re.sub(r'\1', line)
                        if self.cmd_args.backtick_off:
                            line = re.sub(r"(^|[^`])`\$(.+?)\$`", r"\1$\2$", line)
                        self.buffered_markdown.append(line+'\n')

            else:
                # Last line (without newline)
                self.buffered_markdown.append(content)
                content = ''

        self.process_buffer()

        for key, new_link in self.exported_refs.items():
            if key not in self.image_refs:
                print('WARNING Exported orphan ref %s as file %s' % (key, new_link), file=sys.stderr)

        if self.imported_defs:
            # Output imported ref definitions
            self.output.append('\n')
            for link, title in self.imported_defs:
                new_key, new_link = self.imported_defs[(link, title)]
                self.output.append('[%s]: %s%s\n' % (new_key, new_link, quote_pad_title(title,parentheses=True)))

        return ''.join(self.output)

    def gen_filename(self, content_type=''):
        label = generate_random_label()
        if content_type.startswith('image/'):
            filename = 'image-' + label + '.' + content_type.split('/')[1]
        else:
            filename = 'file-' + label
            if content_type:
                filename += '.' + content_type.split('/')[0]
        return filename

    def import_link(self, link, title=''):
        """Import link as data URL, return (filename, new_title, new_link). On error, return None, None, None"""
        if link in self.imported_links:
            filename, content_type, content = self.imported_links[link]
        else:
            filename, content_type, content = self.get_link_data(link, data_url=True)
            if filename is None:
                return None, None, None

        title_filename = self.get_html_tag_attr('file', ' '+title)
        filename = filename or title_filename
        if not filename:
            filename = self.gen_filename(content_type)

        file_attr = 'file='+filename
        if not title_filename:
            # Include filename attribute in title
            if not title:
                new_title = file_attr
            else:
                new_title = ' ' + file_attr
        else:
            new_title = title

        self.imported_links[link] = (filename, content_type, content)
        return filename, new_title, content

    def import_ref(self, link, title, key=''):
        """Return (key, new_title, new_link). On error, return None, None, None"""
        filename, new_title, new_link = self.import_link(link)
        if filename is None:
            return None, None, None

        if key:
            new_key = key
        else:
            # Check if link has already been imported (with the same title)
            new_key, new_link = self.imported_defs.get( (link, title), (None, None) )
            if new_key:
                return new_key, new_title, new_link

        if not new_key:
            # Generate new key from filename
            new_key = make_id_from_text(filename)
            suffix = ''
            if new_key in self.imported_refs:
                j = 2
                while new_key+'-'+str(j) in self.imported_refs:
                    j += 1
                new_key += '-' + str(j)

        self.imported_refs[new_key] = (link, title)
        self.imported_defs[(link, title)] = (new_key, new_link)
        print('Imported ref %s as %s' % (link, new_key), file=sys.stderr)
        return new_key, new_title, new_link

    def export_ref_definition(self, key, link, title, dry_run=False):
        """Return (key, new_link, new_title). On error, return None, None, None"""
        try:
            filename, content_type, content = self.get_link_data(link)
            if filename is None or not content_type or not content_type.startswith('image/'):
                raise Exception('Unable to retrieve image %s' % link)

            # Create new link to local file
            new_link = make_id_from_text(filename)
            if title:
                new_link = make_id_from_text(self.get_html_tag_attr('file', ' '+title)) or new_link

            new_link = new_link or self.gen_filename(content_type=content_type)

            if self.cmd_args.image_dir:
                new_link = self.cmd_args.image_dir+'/'+new_link

            if self.cmd_args.dest_dir:
                fpath = self.cmd_args.dest_dir + '/' + new_link
            else:
                fpath = new_link

            self.write_content(fpath, content, dry_run=dry_run)
            print('Exported ref %s as file %s' % (key, fpath), file=sys.stderr)
            return key, new_link, title
        except Exception, excp:
            print('ERROR in exporting ref %s as file: %s' % (key, excp), file=sys.stderr)
            return None, None, None

    def hrule(self, text):
        if 'rule' not in self.cmd_args.strip and 'markup' not in self.cmd_args.strip:
            self.buffered_markdown.append(text+'\n\n')
        self.skipping_notes = False

    def minirule(self, text):
        if 'rule' not in self.cmd_args.strip and 'markup' not in self.cmd_args.strip:
            self.buffered_markdown.append(text+'\n\n')

    def math_block(self, content, latex=False):
        if 'markup' not in self.cmd_args.strip:
            if latex or not self.cmd_args.backtick_on:
                self.output.append(content)
            else:
                self.output.append("`"+content+"`")

    def process_buffer(self):
        if not self.buffered_markdown:
            return
        md_text = ''.join(self.buffered_markdown)
        self.buffered_markdown = []

        md_text = self.link_re.sub(self.external_link, md_text)
        md_text = self.reflink_re.sub(self.ref_link, md_text)
        md_text = self.img_re.sub(self.img_tag, md_text)

        if 'markup' not in self.cmd_args.strip:
            self.output.append(md_text)


class ArgsObj(object):
    def __init__(self, str_args=[], bool_args=[], defaults={}):
        """List of string args, bool args and dictionary of non-null/False defaults"""
        self.str_args = str_args
        self.bool_args = bool_args
        self.defaults = defaults
        self.ParserArgs = namedtuple('ParserArgs', self.str_args + self.bool_args)

    def create_args(self, *args, **kwargs):
        """Returns a named tuple with argument values, optionally initialized from object args[0] (if not None) and updated with kwargs"""
        if args and args[0] is not None:
            arg_vals = dict( [(k, getattr(args[0], k)) for k in self.str_args+self.bool_args] )
        else:
            arg_vals = dict( [(k, '') for k in self.str_args] + [(k, False) for k in self.bool_args] )
            arg_vals.update(self.defaults)
        arg_vals.update(kwargs)

        return self.ParserArgs(**arg_vals)

Args_obj = ArgsObj( str_args= ['dest_dir', 'image_dir', 'image_url', 'images', 'strip'],
                    bool_args= ['backtick_off', 'backtick_on', 'fence', 'keep_annotation', 'overwrite', 'unfence'],
                    defaults= {'image_dir': 'images'})

def make_strip_set(strip_arg, strip_all):
    strip_all_set = set(strip_all)
    strip_set = set(strip_arg.split(',')) if strip_arg else set()
    if 'all' in strip_set:
        strip_set.discard('all')
        if 'but' in strip_set:
            strip_set.discard('but')
            strip_set = strip_all_set.copy().difference(strip_set)
        else:
            strip_set = strip_all_set.copy()    
    return strip_set

if __name__ == '__main__':
    import argparse

    strip_all = ['answers', 'code', 'concepts', 'extensions', 'markup', 'notes', 'rule']
    
    parser = argparse.ArgumentParser(description='Convert from Markdown to Markdown')
    parser.add_argument('--backtick_off', help='Remove backticks bracketing inline math', action="store_true")
    parser.add_argument('--backtick_on', help='Wrap block math with backticks', action="store_true")
    parser.add_argument('--dest_dir', help='Destination directory for creating files (default:'')', default='')
    parser.add_argument('--fence', help='Convert indented code blocks to fenced blocks', action="store_true")
    parser.add_argument('--image_dir', help='image subdirectory (default: "images")', default='images')
    parser.add_argument('--image_url', help='URL prefix for images, including image_dir')
    parser.add_argument('--images', help='images=(check|copy||export|import)[,embed,web,pandoc] to process images', default='')
    parser.add_argument('--keep_annotation', help='Keep annotation', action="store_true")
    parser.add_argument('--overwrite', help='Overwrite files', action="store_true")
    parser.add_argument('--strip', help='Strip %s|all|all,but,...' % ','.join(strip_all))
    parser.add_argument('--unfence', help='Convert fenced code block to indented blocks', action="store_true")
    parser.add_argument('file', help='Markdown filename', type=argparse.FileType('r'), nargs=argparse.ONE_OR_MORE)
    cmd_args = parser.parse_args()

    if cmd_args.image_url and not cmd_args.image_url.endswith('/'):
        cmd_args.image_url += '/'
    cmd_args.images = set(cmd_args.images.split(',')) if cmd_args.images else set()

    cmd_args.strip = make_strip_set(cmd_args.strip, strip_all)

    md_parser = Parser( Args_obj.create_args(cmd_args) )   # Use args_obj to pass orgs as a consistency check
    
    fnames = []
    for f in cmd_args.file:
        fcomp = os.path.splitext(os.path.basename(f.name))
        fnames.append(fcomp[0])
        if fcomp[1] != '.md':
            sys.exit('Invalid file extension for '+f.name)

        if os.path.exists(fcomp[0]+'-modified.md') and not cmd_args.overwrite:
            sys.exit("File %s-modified.md already exists. Delete it or specify --overwrite" % fcomp[0])

    for j, f in enumerate(cmd_args.file):
        filepath = f.name
        md_text = f.read()
        f.close()
        modified_text = md_parser.parse(md_text, filepath)

        outname = fnames[j]+"-modified.md"
        write_file(outname, modified_text)
        print("Created ", outname, file=sys.stderr)
            