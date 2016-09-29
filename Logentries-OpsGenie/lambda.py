#!/usr/bin/python

import urllib
import json
import requests
import io
import datetime

# Search all the logs in a given Logentries account for the LEQL query provided.

# This script leverages the Logentries REST API POST Query
# Documentation: https://docs.logentries.com/docs/post-query

apiKey = 'YOUR API KEY GOES HERE'  # A Logentries Read-Only key is recommended.
accountKey = 'YOUR ACCOUNT KEY GOES HERE'  # From the profile tab in the Account section.
timeRange = 'Last 20 minutes'  # The search window to run the LEQl query over.
# days, hours, minutes, and seconds are all acceptable. e.g. Last 5 days

opsGenieApiKey = '[YOUR OPSGENIE INTEGRATION API KEY]'  # Api Key of the integration on OpsGenie.
opsGenieApiURL = 'https://api.opsgenie.com'  # End-point URL for OpsGenie.
htmlFilePath = "/tmp/logEntries.html"  # Path of the file that will be created and then attached to the alert.


def lambda_handler(event):
    ops_genie_alertid = event['alert']['alertId']
    action = event["action"]

    # Check the action of the alert, discard if it's not Create or queryLogs.
    if str(action) != "Create" and str(action) != "queryLogs":
        response = {"Status": "Ignoring Request"}
        return response

    def get_query_string_from_alert():
        # Get the query string from the alert's extra properties.

        req = requests.get(opsGenieApiURL + "/v1/json/alert?apiKey=" + opsGenieApiKey + "&id=" + ops_genie_alertid)
        alert = req.json()
        details = alert['details']
        query_string = details['queryString']

        return query_string

    def create_html_file(content):
        # Create html file from template with given content in htmlFilePath.

        with io.FileIO(htmlFilePath, "w") as f:
            f.write("""
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <title>LogEntries</title>
    </head>
    <body>
    <table border="5" align="center" style="border-top-color: aqua; border-bottom-color: aqua; border-left-color: cornflowerblue; border-right-color: cornflowerblue; table-layout:fixed; width: 100%">
    <tr>
        <th style="width: 100px">Timestamp</th>
        <th>Message</th>
    </tr>
    """)
            f.write(content)
            f.write("""
    </table>
    </body>
    </html>
    """)
            f.close()

    def attach_file_to_alert():
        # Do a post request to OpsGenie to attach created html file to the alert.

        req = requests.post(opsGenieApiURL + "/v1/json/alert/attach",
                            data={"apiKey": opsGenieApiKey, "id": ops_genie_alertid},
                            files={"attachment": open(htmlFilePath, "rb")})
        return req.json()

    leqlquery = get_query_string_from_alert()

    def get_host_name(accountkey):
        # Get all log sets in the account

        dict_host_names_keys = {}

        req = urllib.urlopen('https://api.logentries.com/' + accountkey + '/hosts/')

        resp = json.load(req)
        for hosts in resp['list']:
            dict_host_names_keys[hosts['key']] = hosts['name']

        return dict_host_names_keys

    def get_logs_names(accountkey, dict_host_names_keys):
        # Get all logs in the account

        dict_logs_names_keys = {}

        for k, v in dict_host_names_keys.iteritems():
            if v != r'Inactivity Alerts':
                req = urllib.urlopen('http://api.logentries.com/' + accountkey + '/hosts/' + k + '/')
                resp = json.load(req)
                for logs in resp['list']:
                    dict_logs_names_keys[logs['key']] = logs['name']
        return dict_logs_names_keys

    def continue_request(req):
        if 'links' in req.json():
            continue_url = req.json()['links'][0]['href']
            new_response = fetch_results(continue_url)
            handle_response(new_response)

    def fetch_results(provided_url):
        """
        Make the get request to the url and return the response.
        """
        try:
            resp = requests.get(provided_url, headers={'x-api-key': apiKey})
            return resp
        except requests.exceptions.RequestException as error:
            print error

    def handle_response(resp):
        if resp.status_code == 200 or resp.status_code == 202:
            if 'events' in response.json():
                content = ""

                for logevent in response.json()['events']:
                    log_timestamp = logevent["timestamp"]

                    log_time = datetime.datetime.fromtimestamp(int(log_timestamp)/1000.0).strftime('%Y-%m-%d %H:%M:%S')

                    content += "<tr><td align=\"center\">"
                    content += str(log_time)
                    content += "</td><td style=\"word-wrap: break-word\">"

                    for key, val in json.loads(logevent["message"]).iteritems():
                        content += str(key) + "=" + str(val) + ", "

                    content += "</td></tr>"

                    print(json.dumps(logevent, indent=4).decode('string_escape'))

                create_html_file(content)
            if 'links' in resp.json():
                continue_request(resp)
            else:
                print json.dumps(resp.json(), indent=4, separators={':', ';'})
        else:
            print 'Error status code ' + str(resp.status_code)
            return

    def post_query(log_keys, url=None):
        uri = url
        body = None
        if not url:
            data = """
                {
                    "logs": ["""

            for k in log_keys:
                data += "\"" + str(k) + "\", "

            data = data[:-2]

            data += """
                    ],
                    "leql": {
                        "during": {"""
            data += "\"time_range\": \"" + timeRange + "\"" + """
                        },"""
            data += "\"statement\": \"" + leqlquery + "\"" + """
                    }
                }
            """

            body = json.loads(data)

            uri = 'https://rest.logentries.com/query/logs/'
        headers = {'x-api-key': apiKey}
        r = requests.post(uri, json=body, headers=headers)
        handle_response(r)
        print r.status_code, r.content

    hosts = get_host_name(accountKey)
    logs = get_logs_names(accountKey, hosts)

    log_keys_list = []

    for log_key in logs.iterkeys():
        log_keys_list.append(log_key)

    post_query(log_keys_list)

    attach_file_to_alert()

    return {"Status": "Script completed successfully"}
