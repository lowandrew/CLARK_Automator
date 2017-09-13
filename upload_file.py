from RedmineAPI import Access
from RedmineAPI import Utilities
from RedmineAPI import RedmineAPI

import sys

# Setup redmine access so files can be uploaded.
timelog = Utilities.create_time_log()  # I think this is necessary
redmine = Access.RedmineAccess(timelog, 'INSERT API KEY HERE')  # Un-hardcode this at some point.

# Upload the file to Redmine.
redmine.redmine_api.upload_file('reports/abundance.xlsx', int(sys.argv[1]), 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
                                file_name_once_uploaded=sys.argv[1] + '_abundance.xlsx')