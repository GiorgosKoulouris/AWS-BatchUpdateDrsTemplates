import pandas as pd
import boto3
import argparse
import datetime
import subprocess
import sys


def logActions(level, short_desc, long_desc):
    """Formats and prints logs

    :param level: Log level (INF,ERR)
    :type level: string
    :param short_desc: Short log message
    :type short_desc: string
    :param long_desc: Long log message
    :type long_desc: string
    """
    
    dt_object = datetime.datetime.now()
    dt_string = dt_object.strftime("%m/%d/%Y %H:%M:%S")
    prefix = f"{dt_string} - {level}:"
    print(f"{prefix} {short_desc}")
    if long_desc:
        print(f"{prefix} {long_desc}")


def init_aws_clients(region):
    """Initializes EC2 and DRS boto clients

    :param region: AWS Region
    :type region: string
    :return: DRS client, EC2 client
    :rtype: boto_client, boto_client
    """
    
    try:
        if region == None:
            drs_client = boto3.client("drs")
            ec2_client = boto3.client("ec2")
        else:
            drs_client = boto3.client("drs", region_name=region)
            ec2_client = boto3.client("ec2", region_name=region)

        logActions("INF", "Successfully created AWS clients", None)
        return drs_client, ec2_client
    except Exception as e:
        logActions("ERR", "Failed to create AWS clients", e)
        exit(1)


def get_excel_data(file_path):
    """Reads data from XLS and returns the respective lists

    :param file_path: Path to the XLS doc
    :type file_path: string
    :return: drs_df, mod_df, vol_dfs
    :rtype: list, list, list
    """
    try:
        drs_df = pd.read_excel(file_path, sheet_name="DRS_Details")
        mod_df = pd.read_excel(file_path, sheet_name="Mod_TemplateConfigs")
        vol_dfs = pd.read_excel(file_path, sheet_name="Mod_VolumeConfigs")

        logActions("INF", f"Successfully parsed XLS document ({file_path})", None)
        return drs_df, mod_df, vol_dfs

    except Exception as e:
        logActions("ERR", f"Failed to parse XLS document ({file_path})", e)
        exit(1)


def update_launch_templates(drs_df, mod_df, vol_dfs):
    """Makes the modification of the launch templates

    :param drs_df: DRS related data
    :type drs_df: list
    :param mod_df: Modification related data
    :type mod_df: list
    :param vol_dfs: Volume related data
    :type vol_dfs: list
    :return: True if any update occured, False if otherwise
    :rtype: boolean
    """
    
    has_any_updates = False
    for index, row in drs_df.iterrows():
        try:
            new_vols = {}
            ss_id = row["SourceServerID"]
            template_id = row["TemplateID"]
            template_version = row["TemplateVersion"]
            instance_id = row["OriginInstanceID"]
            hostname = row["SourceServerName"]

            lc = drs_client.get_launch_configuration(sourceServerID=ss_id)

            ltv = ec2_client.describe_launch_template_versions(
                LaunchTemplateId=template_id, Versions=[str(template_version)]
            )["LaunchTemplateVersions"][0]

            ltv_data = ltv["LaunchTemplateData"]

            new_subnet_id = mod_df.loc[
                mod_df["OriginInstanceID"] == instance_id, "New_DrsSubnetID"
            ].squeeze()
            new_launch_state = mod_df.loc[
                mod_df["OriginInstanceID"] == instance_id, "New_LaunchState"
            ].squeeze()
            new_copy_private_ip = mod_df.loc[
                mod_df["OriginInstanceID"] == instance_id, "New_CopyPrivateIP"
            ].squeeze()
            new_private_ips = mod_df.loc[
                mod_df["OriginInstanceID"] == instance_id, "New_PrivateIPs"
            ].squeeze()
            new_rightsizing = mod_df.loc[
                mod_df["OriginInstanceID"] == instance_id, "New_RightSizing"
            ].squeeze()
            new_instance_type = mod_df.loc[
                mod_df["OriginInstanceID"] == instance_id, "New_InstanceType"
            ].squeeze()
            new_sg_ids = mod_df.loc[
                mod_df["OriginInstanceID"] == instance_id, "New_SecurityGroupIDs"
            ].squeeze()

            vol_df = vol_dfs[vol_dfs["OriginInstanceID"] == instance_id]
            for vol_index, vol_row in vol_df.iterrows():
                vol_dev_name = vol_row["DRS_DeviceName"]
                new_vols[vol_dev_name] = {
                    "NewType": (
                        vol_row["New_Type"]
                        if not pd.isnull(vol_row["New_Type"])
                        else ""
                    ),
                    "NewIOPS": (
                        vol_row["New_IOPS"]
                        if not pd.isnull(vol_row["New_IOPS"])
                        else ""
                    ),
                    "NewThroughput": (
                        vol_row["New_Throughput"]
                        if not pd.isnull(vol_row["New_Throughput"])
                        else ""
                    ),
                }

            lc_modified = False
            lt_modified = False
            if not pd.isnull(new_launch_state):
                new_value = new_launch_state.upper()
                if new_value not in ["STARTED", "STOPPED"]:
                    lc_modified = False
                    lt_modified = False
                    raise Exception(
                        f"Invalid new launch state for {hostname}. Valid options: <STARTED|STOPPED>"
                    )
                elif lc["launchDisposition"].upper() != new_value:
                    lc["launchDisposition"] = new_value
                    lc_modified = True

            if not pd.isnull(new_copy_private_ip):
                new_value = new_copy_private_ip
                if str(new_value).upper() not in ["TRUE", "FALSE"]:
                    lc_modified = False
                    lt_modified = False
                    raise Exception(
                        f"Invalid new copy private IP value for {hostname}. Valid options: <TRUE|FALSE>"
                    )
                elif str(lc["copyPrivateIp"]).upper() != str(new_value).upper():
                    lc["copyPrivateIp"] = bool(new_copy_private_ip)
                    lc_modified = True

            if not pd.isnull(new_rightsizing):
                new_value = new_rightsizing.upper()
                if new_value not in ["NO", "BASIC", "IN_AWS"]:
                    lc_modified = False
                    lt_modified = False
                    raise Exception(
                        f"Invalid new rightsizing value for {hostname}. Valid options: <NO|BASIC|IN_AWS>"
                    )
                else:
                    if new_value == "NO":
                        new_value = "NONE"
                    if lc["targetInstanceTypeRightSizingMethod"].upper() != new_value:
                        lc["targetInstanceTypeRightSizingMethod"] = new_value
                        lc_modified = True

            if not pd.isnull(new_subnet_id):
                if ltv_data["NetworkInterfaces"][0]["SubnetId"] != new_subnet_id:
                    ltv_data["NetworkInterfaces"][0]["SubnetId"] = new_subnet_id
                    lt_modified = True

            if not pd.isnull(new_private_ips):
                if lc["copyPrivateIp"] != "TRUE":
                    ip_data = []
                    ips_array = new_private_ips.split(",")
                    ip_index = 0
                    for ip in ips_array:
                        if ip_index == 0:
                            is_primary = True
                        else:
                            is_primary = False
                        ip_data.append(
                            {"Primary": is_primary, "PrivateIpAddress": ip.strip()}
                        )
                        ip_index += 1
                    if (
                        ltv_data["NetworkInterfaces"][0]["PrivateIpAddresses"]
                        != ip_data
                    ):
                        ltv_data["NetworkInterfaces"][0]["PrivateIpAddresses"] = ip_data
                        lt_modified = True

            if not pd.isnull(new_sg_ids):
                old_sgs = ltv_data["NetworkInterfaces"][0]["Groups"]
                old_sgs.sort()
                sg_array_tmp = new_sg_ids.split(",")
                sg_array = []
                for sg in sg_array_tmp:
                    sg_array.append(sg.strip())
                sg_array.sort()
                if old_sgs != sg_array:
                    ltv_data["NetworkInterfaces"][0]["Groups"] = []
                    for sg_id in sg_array:
                        ltv_data["NetworkInterfaces"][0]["Groups"].append(sg_id)
                    lt_modified = True

            if not pd.isnull(new_instance_type):
                if lc["targetInstanceTypeRightSizingMethod"].upper() == "NONE":
                    if ltv_data["InstanceType"] != new_instance_type:
                        ltv_data["InstanceType"] = new_instance_type
                        lt_modified = True

            for ltv_vol in ltv_data["BlockDeviceMappings"]:
                dev_name = ltv_vol["DeviceName"]
                if new_vols[dev_name]["NewType"] != "":
                    if (
                        ltv_vol["Ebs"]["VolumeType"].upper()
                        != new_vols[dev_name]["NewType"].upper()
                    ):
                        ltv_vol["Ebs"]["VolumeType"] = new_vols[dev_name]["NewType"]
                        lt_modified = True
                if new_vols[dev_name]["NewIOPS"] != "":
                    if ltv_vol["Ebs"]["Iops"] != new_vols[dev_name]["NewIOPS"]:
                        ltv_vol["Ebs"]["Iops"] = int(new_vols[dev_name]["NewIOPS"])
                        lt_modified = True
                if new_vols[dev_name]["NewThroughput"] != "":
                    if (
                        ltv_vol["Ebs"]["Throughput"]
                        != new_vols[dev_name]["NewThroughput"]
                    ):
                        ltv_vol["Ebs"]["Throughput"] = int(
                            new_vols[dev_name]["NewThroughput"]
                        )
                        lt_modified = True

            for tag_spec in ltv_data["TagSpecifications"]:
                if tag_spec["ResourceType"] == "instance":
                    tag_exists = False
                    for tag in tag_spec["Tags"]:
                        if tag["Key"] == "protera_status":
                            tag["Value"] = "newbuild"
                            tag_exists = True
                    if not tag_exists:
                        tag_spec["Tags"].append(
                            {"Key": "protera_status", "Value": "newbuild"}
                        )
                        lt_modified = True

            # Modify the launch template only if modifications were found
            if lt_modified:
                new_version_response = ec2_client.create_launch_template_version(
                    LaunchTemplateId=template_id, LaunchTemplateData=ltv_data
                )
                new_version_number = new_version_response["LaunchTemplateVersion"][
                    "VersionNumber"
                ]
                response = ec2_client.modify_launch_template(
                    LaunchTemplateId=template_id, DefaultVersion=str(new_version_number)
                )
                logActions(
                    "INF", f"Updated launch template for {ss_id} ({hostname})", None
                )
            else:
                logActions(
                    "INF",
                    f"No changes on launch template for {ss_id} ({hostname})",
                    None,
                )

            # Modify the launch configuration only if modifications were found
            if lc_modified:
                response = drs_client.update_launch_configuration(
                    sourceServerID=ss_id,
                    copyPrivateIp=lc["copyPrivateIp"],
                    targetInstanceTypeRightSizingMethod=lc[
                        "targetInstanceTypeRightSizingMethod"
                    ],
                    launchDisposition=lc["launchDisposition"],
                )
                logActions(
                    "INF",
                    f"Updated launch configuration for {ss_id} ({hostname})",
                    None,
                )
            else:
                logActions(
                    "INF",
                    f"No changes on launch configuration for {ss_id} ({hostname})",
                    None,
                )

            if lc_modified or lt_modified:
                has_any_updates = True

        except Exception as e:
            logActions("ERR", f"Failed to update template for {ss_id} ({hostname})", e)

    return has_any_updates


def fetch_updated_data(file_path, region):
    """Retrieves updated DRS data and re-populates the data on the XLS doc

    :param file_path: Path to the XLS doc
    :type file_path: string
    :param region: AWS region
    :type region: string
    """
    
    try:
        subprocess.run(
            [
                sys.executable,
                "parse_drs_info.py",
                "--workbook-path",
                file_path,
                "--region",
                region,
            ]
        )
        logActions(
            "INF",
            f"Successfully stored updated data for DRS on spreadsheet ({file_path})",
            None,
        )
        subprocess.run(
            [sys.executable, "create-mod-sheets.py", "--workbook-path", file_path]
        )
        logActions(
            "INF",
            f"Successfully created updated mod sheets on XLS document ({file_path})",
            None,
        )
    except Exception as e:
        logActions(
            "ERR",
            f"Failed to update the XLS document with the updated data ({file_path})",
            e,
        )


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

    # Not providing '--workbook-path' option defaults in './DRS_Templates.xlsx'
    if file_path == None:
        file_path = "DRS_Templates.xlsx"

    drs_client, ec2_client = init_aws_clients(region)
    drs_df, mod_df, vol_dfs = get_excel_data(file_path)
    has_any_updates = update_launch_templates(drs_df, mod_df, vol_dfs)
    
    # If any launch configuration or launch template was modified, fetch the updated data and update XLS
    if has_any_updates:
        fetch_updated_data(file_path, region)
    logActions("INF", f"Execution finished", None)
