import pandas as pd
import boto3
import argparse
import datetime

def logActions(level, short_desc, long_desc):
    dt_object = datetime.datetime.now()
    dt_string = dt_object.strftime("%m/%d/%Y %H:%M:%S")
    prefix = f"{dt_string} - {level}:"
    print(f"{prefix} {short_desc}")
    if long_desc:
        print(f"{prefix} {long_desc}")

def init_aws_client(region):
    try:
        if region == None:
            drs_client = boto3.client("drs")
        else:
            drs_client = boto3.client("drs", region_name=region)

        logActions("INF", "Successfully created AWS client", None)
        return drs_client
    except Exception as e:
        logActions("ERR", "Failed to create AWS client", e)
        exit(1)

def get_server_list(drs_client):
    try:
        # Fetch source servers
        response = drs_client.describe_source_servers()
        
        # Process each source server and extract the ID and Name tag value
        source_servers = response.get('items', [])
        ss_list = []

        for server in source_servers:
            
            server_id = server['sourceServerID']
            source_hostname = server["tags"]["Name"]

            ss_list.append({
                'SourceServerID': server_id,
                'Hostname': source_hostname
            })
            logActions("INF", f"Fetched source server {server_id} ({source_hostname})", None)

        return ss_list

    except Exception as e:
        logActions("INF", f"Failed to fetch source servers", f"{e}")
        exit(1)

def update_workbook(
    server_list, file_path
):
    try:
        ss_list_df = pd.DataFrame(server_list)
        with pd.ExcelWriter(
            file_path, engine="openpyxl", mode="w"
        ) as writer:
            ss_list_df.to_excel(writer, sheet_name="All_Servers", index=False)
            ss_list_df.to_excel(writer, sheet_name="List", index=False)

        logActions("INF", f"Successfully updated XLS document ({file_path})", None)
    except Exception as e:
        logActions("ERR", f"Failed to update XLS document ({file_path})", e)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--region", type=str, required=False, help="Name of the DR Region"
    )
    parser.add_argument(
        "--workbook-path", type=str, required=False, help="Path to the XLSX file"
    )
    # Parse the arguments
    args = parser.parse_args()
    region = args.region
    file_path = args.workbook_path

    if file_path == None:
        file_path = "DRS_Templates.xlsx"

    drs_client = init_aws_client(region)
    server_list = get_server_list(drs_client)
    update_workbook(
        server_list, file_path
    )
    logActions("INF", f"Execution finished", None)
