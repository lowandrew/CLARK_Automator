from RedmineAPI.Utilities import FileExtension, create_time_log
import os
from RedmineAPI.Access import RedmineAccess
from RedmineAPI.Configuration import Setup
import shutil
import glob

from Utilities import CustomKeys, CustomValues


def verify_fasta_files_present(seqid_list, fasta_dir):
    missing_fastas = list()
    for seqid in seqid_list:
        if len(glob.glob(fasta_dir + '/' + seqid + '*.fasta')) == 0:
            missing_fastas.append(seqid)
    return missing_fastas


def verify_fastq_files_present(seqid_list, fastq_dir):
    """
    Makes sure that FASTQ files specified in seqid_list have been successfully copied/linked to directory specified
    by fastq_dir.
    :param seqid_list: List with SEQIDs.
    :param fastq_dir: Directory that FASTQ files (both forward and reverse reads should have been copied to
    :return: List of SEQIDs that did not have files associated with them.
    """
    missing_fastqs = list()
    for seqid in seqid_list:
        # Check forward.
        if len(glob.glob(fastq_dir + '/' + seqid + '*R1*fastq*')) == 0:
            missing_fastqs.append(seqid)
        # Check reverse. Only add to list of missing if forward wasn't present.
        if len(glob.glob(fastq_dir + '/' + seqid + '*R2*fastq*')) == 0 and seqid not in missing_fastqs:
            missing_fastqs.append(seqid)
    return missing_fastqs


class Automate(object):

    def __init__(self, force):

        # create a log, can be written to as the process continues
        self.timelog = create_time_log(FileExtension.runner_log)

        # Key: used to index the value to the config file for setup
        # Value: 3 Item Tuple ("default value", ask user" - i.e. True/False, "type of value" - i.e. str, int....)
        # A value of None is the default for all parts except for "Ask" which is True
        # custom_terms = {CustomKeys.key_name: (CustomValues.value_name, True, str)}  # *** can be more than 1 ***
        custom_terms = dict()

        # Create a RedmineAPI setup object to create/read/write to the config file and get default arguments
        setup = Setup(time_log=self.timelog, custom_terms=custom_terms)
        setup.set_api_key(force)

        # Custom terms saved to the config after getting user input
        # self.custom_values = setup.get_custom_term_values()
        # *** can be multiple custom values variable, just use the key from above to reference the inputted value ***
        # self.your_custom_value_name = self.custom_values[CustomKeys.key_name]

        # Default terms saved to the config after getting user input
        self.seconds_between_checks = setup.seconds_between_check
        self.nas_mnt = setup.nas_mnt
        self.redmine_api_key = setup.api_key

        # Initialize Redmine wrapper
        self.access_redmine = RedmineAccess(self.timelog, self.redmine_api_key)

        self.botmsg = '\n\n_I am a bot. This action was performed automatically._'  # sets bot message
        # Subject name and Status to be searched on Redmine
        self.issue_title = 'autoclark'  # must be a lower case string to validate properly
        self.issue_status = 'New'

    def timed_retrieve(self):
        """
        Continuously search Redmine in intervals for the inputted period of time, 
        Log errors to the log file as they occur
        """
        import time
        while True:
            # Get issues matching the issue status and subject
            found_issues = self.access_redmine.retrieve_issues(self.issue_status, self.issue_title)
            # Respond to the issues in the list 1 at a time
            while len(found_issues) > 0:
                self.respond_to_issue(found_issues.pop(len(found_issues) - 1))
            self.timelog.time_print("Waiting for the next check.")
            time.sleep(self.seconds_between_checks)

    def respond_to_issue(self, issue):
        """
        Run the desired automation process on the inputted issue, if there is an error update the author
        :param issue: Specified Redmine issue information
        """
        self.timelog.time_print("Found a request to run. Subject: %s. ID: %s" % (issue.subject, str(issue.id)))
        self.timelog.time_print("Adding to the list of responded to requests.")
        self.access_redmine.log_new_issue(issue)

        try:
            issue.redmine_msg = "Beginning the process for: %s" % issue.subject
            self.access_redmine.update_status_inprogress(issue, self.botmsg)
            ##########################################################################################
            issue.redmine_msg = ''
            print("Getting CLARK automation going.")
            os.makedirs('/mnt/nas/bio_requests/' + str(issue.id))
            # Remember the directory we're in.
            work_dir = os.path.join('/mnt/nas/bio_requests', str(issue.id))
            current_dir = os.getcwd()
            des = issue.description.split('\n')
            seqids = list()
            fasta = False
            for item in des:
                item = item.upper()
                if 'FASTA' in item.rstrip():
                    fasta = True
                    continue
                seqids.append(item.rstrip())
            f = open(work_dir + '/seqid.txt', 'w')
            for seqid in seqids:
                f.write(seqid + '\n')
            f.close()
            # If we're looking at a FASTQ request, try to get the files specified by SEQIDs, and then
            # check that they were successfully extracted. Warn users if we couldn't find FASTQ files for
            # SEQIDs that they specified.
            if not fasta:
                os.chdir('/mnt/nas/MiSeq_Backup')
                cmd = 'python2 /mnt/nas/MiSeq_Backup/file_linker.py {}/seqid.txt {}'.format(work_dir, work_dir)
                os.system(cmd)
                os.chdir(current_dir)
                missing_fastqs = verify_fastq_files_present(seqids, work_dir)
                if len(missing_fastqs) > 0:
                    self.access_redmine.update_issue_to_author(issue, 'WARNING: Could not find FASTQ files for the '
                                                                      'following SEQIDs: {}\nPlease verify that these'
                                                                      ' are valid SEQIDs, create a new issue, and '
                                                                      'try again.'.format(str(missing_fastqs)))
            # If we're looking at a FASTA request, try to get the files specified by SEQIDs, and then
            # check that they were successfully extracted. Warn users if we couldn't find FASTA files for
            # SEQIDs that they specified.
            if fasta:
                cmd = 'python2 /mnt/nas/WGSspades/file_extractor.py {}/seqid.txt {} /mnt/nas/'.format(work_dir, work_dir)
                os.system(cmd)
                missing_fastas = verify_fasta_files_present(seqids, work_dir)
                if len(missing_fastas) > 0:
                    self.access_redmine.update_issue_to_author(issue, 'WARNING: Could not find FASTA files for the '
                                                                      'following SEQIDs: {}\nPlease verify that these'
                                                                      ' are valid SEQIDs, create a new issue, and '
                                                                      'try again.'.format(str(missing_fastas)))
            # Create the shell script we'll use to submit our autoclark job to SLURM.
            f = open('CLARK.sh')
            lines = f.readlines()
            f.close()
            f = open(work_dir + '/' + str(issue.id) + '.sh', 'w')
            for line in lines:
                if 'job_%j' in line:
                    line = line.replace('job', 'biorequest_' + str(issue.id) + '_job')
                f.write(line)
            f.write('python -m metagenomefilter.automateCLARK -s {} -d /mnt/nas/Adam/RefseqDatabase/Bos_taurus/ '
                    '-C /home/ubuntu/Programs/CLARKSCV1.2.3.2/ {}\n'.format(work_dir, work_dir))
            f.write('cd /mnt/nas/bio_requests/{}\n'.format(str(issue.id)))
            f.write('python upload_file.py {}\n'.format(str(issue.id)))
            f.write('rm -rf *.fastq* */*fastq* *.fasta RedmineAPI running_logs *json upload_file.py')
            f.close()

            # Copy files to the biorequest folder that we'll need to upload results to Redmine.
            shutil.copy('upload_file.py', work_dir + '/upload_file.py')
            shutil.copytree('RedmineAPI', work_dir + '/RedmineAPI')
            # Submit the batch script to slurm.
            cmd = 'sbatch {}'.format(work_dir + '/' + str(issue.id) + '.sh')
            os.system(cmd)

            ##########################################################################################
            self.completed_response(issue)

        except Exception as e:
            import traceback
            self.timelog.time_print("[Warning] The automation process had a problem, continuing redmine api anyways.")
            self.timelog.time_print("[Automation Error Dump]\n" + traceback.format_exc())
            # Send response
            issue.redmine_msg = "There was a problem with your request. Please create a new issue on" \
                                " Redmine to re-run it.\n%s" % traceback.format_exc()
            # Set it to feedback and assign it back to the author
            self.access_redmine.update_issue_to_author(issue, self.botmsg)

    def completed_response(self, issue):
        """
        Update the issue back to the author once the process has finished
        :param issue: Specified Redmine issue the process has been completed on
        """
        # Assign the issue back to the Author
        self.timelog.time_print("Assigning the issue: %s back to the author." % str(issue.id))

        issue.redmine_msg = "Your job has been submitted to the OLC Compute Cluster. This issue will be updated" \
                            " with results once the job is complete."
        # Update author on Redmine
        self.access_redmine.update_issue_to_author(issue, self.botmsg)

        # Log the completion of the issue including the message sent to the author
        self.timelog.time_print("\nMessage to author - %s\n" % issue.redmine_msg)
        self.timelog.time_print("Completed Response to issue %s." % str(issue.id))
        self.timelog.time_print("The next request will be processed once available")
