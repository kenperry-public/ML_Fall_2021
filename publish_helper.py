import re
import nbformat

import subprocess
import os
import pathlib
import shlex
import urllib.parse

import pdb

class Publish():
    def __init__(self, **params):
        return

    def cleanFileName(self, fileName):
        fileName = re.sub(r"%20", " ", fileName)
        return fileName

    def isFileName(self, fileName):
        result = True
        if re.search(r"^https?", fileName):
            result = False

        return result

    def QualifyMatches(self, path, m):
        # Add path to the file names in array m
        if len(path) > 0:
            # Remove leading "./", which is redundant with path arg.
            m = [ re.sub(r'^\./',  '', f) for f in m ]

            # Prepend path
            m = [ os.path.join(path, f) for f in m]

        return m
           
        
    def fileToNB(self, nb_file):
        if not os.path.exists(nb_file):
            print("File {f:s} does not exist.".format(f=nb_file))
            return None
                  
        with open(nb_file, 'r') as f:
            nb = nbformat.read(f, 4)

        return nb

    def findNotebookLinks(self, nb):
        results = []
        for i, cell in enumerate( nb['cells'] ):
            # Find links
            links = re.findall(r"\[.*\]\((.+\.ipynb)[^\)]*\)", cell.source)

            results.extend( links )

        return results

    def findImages(self, nb, fs_file, Debug=False):
        results = set()

        # Find path to directory containing fs_file
        (path, _) = os.path.split(fs_file)

        for i, cell in enumerate( nb['cells'] ):
            # Find inline images
            m = re.findall(r"!\[.*\]\(([^\)]+)\)", cell.source)
            results = results.union(m)
            if Debug:
                print("findImages: Image inline Matches: ", "\n".join(m))

            # Find images in html img tag
            m = re.findall(r"<img src=[\"\']?([^ ,\"\'>]+)[\"\']?[^>]*>", cell.source)

            if Debug:
                print("findImages: Image html from file ", fs_file, " in directory ", path, " Matches: ", "\n".join(m))

            # Add path to the file names
            m = self.QualifyMatches(path, m)
           
            results = results.union(m)


        return results
        
    def findNotebookLinksRecursive(self, nb_files, results=None, Debug=False):
        if Debug:
            print("Examining: ", ", ".join(nb_files))

        if results is None:
            results = set()

        # Process all files
        for nb_file in nb_files:
            if nb_file in results:
                if  Debug:
                    print("Already have ", nb_file)
                continue

            results.add(nb_file)

            # Don't examine non-local files
            if not self.isFileName(nb_file):
                print(nb_file,  " is NOT local")
                continue


            # Decode out URL encoding back to text , e.g, %20 to " "
            fs_file = self.cleanFileName(nb_file)

            nb = self.fileToNB( fs_file )
            if nb is None:
                continue

            if Debug:
                print("findNotebookLinksRecursive: examining ", fs_file)
                
            nb_files_in_nb = self.findNotebookLinks(nb)

            # Eliminate links found in the "external" directory
            nb_files_in_nb = [ f for f in nb_files_in_nb
                               if not re.search(r"^external/", f)
                               ]
            
            # What new files were found ?
            nb_files_in_nb = list( set(nb_files_in_nb) - results )
            if Debug:
                print("\n\nIn ", nb_file, " found: ",  ", ".join(nb_files_in_nb))

            # Recursive explore each file found in nb
            if len(nb_files_in_nb) > 0:
                # Add news files found in nb
                if  Debug:
                    print("Examining {f:s}: recursively examine {f1:s}".format(f=nb_file, f1=", ".join(nb_files_in_nb)) )

                # Examine each notebook that we found
                results = self.findNotebookLinksRecursive(list(nb_files_in_nb), results=results)
                # Add notebooks found at this level AFTER having explored each of them (i.e, having gone one level deeper)
                results = results.union( nb_files_in_nb )

        return results

    def findMagic(self, nb, Debug=False):
        results = set()

        for i, cell in enumerate( nb['cells'] ):
            m = re.findall(r"%run +([^\s]+)$", cell.source)
            if Debug and m:
                print("Run", m)
            results = results.union(set(m))

        return results

    def findImport(self, nb, fs_file, Debug=False):
        results = set()

        # Find path to directory containing fs_file
        (path, _) = os.path.split(fs_file)
        
        for i, cell in enumerate( nb['cells'] ):
            m = re.findall(r"%aimport +([^\s]+)\s*", cell.source)
            if Debug and m:
                print("findImport: %aimport from file ", fs_file, " in directory ", path, " Matches: ", "\n".join(m))

            # Add path to the file names
            m = self.QualifyMatches(path, m)
                
            # Add ".py" suffix
            m =[  f + ".py" for f in m ]
            results = results.union(set(m))

        return results

    def findCSV(self, nb, Debug=False):
        results = set()

        for i, cell in enumerate( nb['cells'] ):
            m = re.findall(r'read_csv\(\s*"([^"]+)"\s*\)', cell.source)
            if Debug and m:
                print("read_csv: ", m)

            # Add ".py" suffix
            results = results.union(set(m))

        return results

    def findAll(self, root_nb="Index.ipynb", Debug=False):
        nb_files = self.findNotebookLinksRecursive([root_nb])

        remote_links = set()
        local_links = set()
        image_links = set()
        import_links = set()
        csv_files = set()

        for nb_file in nb_files:
            # Decode out URL encoding back to text , e.g, %20 to " "
            nb_file = urllib.parse.unquote(nb_file)

            # Is it a local notebook, or a remote ?
            if re.search(r"^https?", nb_file):
                # Remote
                # Extract the last part of the link, under assumption that
                # - link is to a github file, with the corresponding file in local directory
                m = re.search(r"^https?.+/([^/]+)$", nb_file)

                file_part = m.group(1)
                if Debug:
                    print("link: ", nb_file, ", local: ",  file_part)           
                remote_links.add(file_part)
            else:
                # Local
                local_links.add(nb_file)

                # Decode out URL encoding back to text , e.g, %20 to " "
                fs_file = self.cleanFileName(nb_file)

                # Find images
                nb = self.fileToNB( fs_file )
                if nb is not None:
                    if Debug:
                        print("findAll: looking for images in ", fs_file)
                        
                    images_in_nb = self.findImages(nb, fs_file)
                    image_links = image_links.union(images_in_nb)

                    # Find target of %run command
                    m_links = self.findMagic(nb)
                    local_links = local_links.union(m_links)

                    # Find target of %aimport command
                    i_links = self.findImport(nb, fs_file)

                              
                    import_links = import_links.union(i_links)

                    # Find target of pd.read_csv()
                    csv = self.findCSV(nb)
                    csv_files = csv_files.union(csv)
                    

        return { "Notebooks": local_links,  
                 "Remote links": remote_links,
                 "Images":  image_links,
                 "Imports": import_links,
                 "CSVs":    csv_files
               }

    def run(self, cmd, Debug=False):
        # Split the command string into tokens
        cmd_tokens = shlex.split(cmd)
        if Debug:
            print("Run: ", cmd)

        p = subprocess.Popen(cmd, shell=True,  stdout=subprocess.PIPE, stderr=subprocess.PIPE, close_fds=True)
        p.wait()

        status, text = p.returncode, p.stdout.read()

        if p.returncode:
            # Popen returns bytes, not string.  Convert
            text = text.decode("utf-8")

            print("{c:s} (rc={r:d}): {m:s}".format(c=cmd, r=p.returncode, m=text))

        return p.returncode

    def run2(self, cmd, Debug=False):
        # Split the command string into tokens
        cmd_tokens = shlex.split(cmd)
        if Debug:
            print("Run: ", cmd)

        p = subprocess.Popen(cmd, shell=True,  stdout=subprocess.PIPE, stderr=subprocess.PIPE, close_fds=True)
        p.wait()

        status, text = p.returncode, p.stdout.read()

        if p.returncode:
            # Popen returns bytes, not string.  Convert
            text = text.decode("utf-8")

            print("{c:s} (rc={r:d}): {m:s}".format(c=cmd, r=p.returncode, m=text))

        return p.returncode
     
    def preview(self, root_nb="Index.ipynb"):
        result = self.findAll(root_nb=root_nb)
        
        print("Notebooks:")
        print ( "\t" + "\n\t".join( sorted(result["Notebooks"])) )

        print("\nImages:\n\t")
        print ( "\t" + "\n\t".join( sorted(result["Images"])) )

        print("\nImports:\n\t")
        print ( "\t" + "\n\t".join( sorted(result["Imports"])) )

        print("\nRemote links:\n\t")
        print ( "\t" + "\n\t".join( sorted(result["Remote links"])) )

        print("\nCSV files:\n\t")
        print("\t" + "\n\t".join( sorted(result["CSVs"])) )
        
    def gitAdd(self, result, Debug=False):
        # Add all references to git
        for ref in ("Notebooks", "Images", "Imports", "Remote links", "CSVs"):
            files = result[ref]
            for file in sorted(files):
                # Don't commit files in "external" sub-directory
                if  re.search(r"^external/", file):
                    print("Not commiting external: ", file)
                    continue


                file = re.sub(r"%20", " ", file)
                cmd = "git add '{f:s}'".format(f=file)
                rc = self.run2(cmd, Debug=Debug)

                if rc != 0:
                    print("{c:s} (rc={r:d})".format(c=cmd, r=rc))

    def to_slides(self, result, Debug=False):
        nb_files = result["Notebooks"]

        for nb_file in sorted(nb_files):
            # Strip off suffix
            m = re.search(r"^([^\.]+).ipynb$", nb_file)

            file_part = m.group(1)
            cmd = "(export BROWSER=google-chrome; jupyter nbconvert --to slides '{f:s}') ".format(f=nb_file)
            
            rc = self.run2(cmd, Debug=Debug)

            if rc == 0:
                browser = "google-chrome --incognito"

                if Debug:
                    print("START ", browser)

                # URL encode file name
                nb_file_q = urllib.parse.quote(nb_file)
                
                slide_file  = re.sub(r".ipynb", ".slides.html", nb_file_q)
                cmd="{b:s} http://127.0.0.1:8000/{f:s}?print-pdf".format(b=browser, f=slide_file)

                rc = self.run2(cmd, Debug = Debug)

            else:
                print("FAILED to convert to slides: ", nb_file)
                
    def to_pdf(self, result, Debug=False):
        nb_files = result["Notebooks"]

        failed = set()
        
        for nb_file in sorted(nb_files):
            # Decode out URL encoding back to text , e.g, %20 to " "
            nb_file = urllib.parse.unquote(nb_file)

            # Strip off suffix
            m = re.search(r"^([^\.]+).ipynb$", nb_file)
            if m is None:
                print("Failed match of file {f:s} with .ipynb tail".format(f=nb_file))
                continue
            
            file_part = m.group(1)

            # Check if pdf is older than source
            update = True
            pdf_file = os.path.join("pdf",file_part + " slides.pdf")

            my_file = pathlib.Path(pdf_file)
            # Is there a corresponding pdf already ?
            if my_file.is_file():
                if Debug:
                    print("\tpdf file exists: {f:}".format(f=pdf_file) )

                # Is the pdf older than source
                if os.path.getmtime(pdf_file) < os.path.getmtime(nb_file):
                    print("\tpdf file needs to be updated: {f:}".format(f=pdf_file) )
                else:
                    update = False

            if not update:
                continue
            
            cmd = "jupyter nbconvert --to pdf '{f:s}'".format(f=nb_file)

            rc = self.run2(cmd, Debug=Debug)

            if rc!= 0:
                if Debug:
                    print("FAILED to convert to pdf: ", nb_file)
                    
                failed = failed.union( { nb_file } )

        return { "failed": failed }


    def publish(self, root_nb="Index.ipynb", git=True, pdf=False, slides=False,  Debug=False):
        # os.chdir( os.path.join( os.environ["HOME"], "Notebooks/NYU") )
        
        result = self.findAll(root_nb=root_nb)

        if git:
            self.gitAdd(result, Debug=Debug)

        if pdf:
            pdf_result = self.to_pdf(result, Debug=Debug)
            failed = pdf_result["failed"]

            # Try converting failed to_pdf to_slides
            if len(failed) > 0:
                print("Try failed to_pdf with to_slides: ", sorted(failed) )
                
                pdf_failed = { "Notebooks": failed }

                self.to_slides( pdf_failed, Debug=Debug)


        if slides:
            self.to_slides(result, Debug=Debug)
