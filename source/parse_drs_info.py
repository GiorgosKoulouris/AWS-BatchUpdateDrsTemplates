import pandas as pd
import boto3
import argparse
import datetime


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
    """Initializes EC2 boto clients

    :param region: AWS Region
    :type region: string
    :return: DRS client, EC2 client
    :rtype: boto_client, boto_client
    """
    
    try:
        drs_client = boto3.client("drs", region_name=region)
        ec2_client = boto3.client("ec2", region_name=region)

        logActions("INF", "Successfully created AWS clients", None)
        return drs_client, ec2_client
    except Exception as e:
        logActions("ERR", "Failed to create AWS clients", e)
        exit(1)


def read_excel(file_path):
    """Reads the source server list from the XLS doc and returns a list

    :param file_path: path to the XLS doc
    :type file_path: string
    :return: Source server list
    :rtype: list
    """
    
    try:
        df = pd.read_excel(file_path, sheet_name="List")
        logActions("INF", f"Successfully parsed XLS document ({file_path})", None)
        return df
    except Exception as e:
        logActions("ERR", f"Failed to parse XLS document ({file_path})", e)
        exit(1)


def get_drs_details(df, drs_client, ec2_client):
    """Returns all info related to DRS source servers

    :param df: Source server list
    :type df: list
    :param drs_client: DRS boto client
    :type drs_client: boto_client
    :param ec2_client: EC2 boto client
    :type ec2_client: boto_client
    :return: ss_list, ss_total_info, volumes, security_rules
    :rtype: list, list, list, list
    """
    
    ss_list = []
    ss_total_info = []
    volumes = []
    security_rules = []
    for ss_id in df["SourceServerID"]:
        ss_volumes = []
        ss_info = {}

        try:
            ss = drs_client.describe_source_servers(
                filters={"sourceServerIDs": [ss_id]}
            )
            source_instance_id = ss["items"][0]["sourceProperties"][
                "identificationHints"
            ]["awsInstanceID"]
            source_instance_name = ss["items"][0]["tags"]["Name"]

            lc = drs_client.get_launch_configuration(sourceServerID=ss_id)
            lt_id = lc["ec2LaunchTemplateID"]

            lt = ec2_client.describe_launch_templates(LaunchTemplateIds=[lt_id])
            default_lt_version = lt["LaunchTemplates"][0]["DefaultVersionNumber"]

            lt_data = ec2_client.describe_launch_template_versions(
                LaunchTemplateId=lt_id, Versions=[str(default_lt_version)]
            )["LaunchTemplateVersions"][0]["LaunchTemplateData"]

            instance_type = lt_data["InstanceType"]

            subnet_id = lt_data["NetworkInterfaces"][0]["SubnetId"]
            subnet = ec2_client.describe_subnets(SubnetIds=[subnet_id])
            subnet_tags = subnet["Subnets"][0].get("Tags", [])
            subnet_name = next(
                (tag["Value"] for tag in subnet_tags if tag["Key"] == "Name"), subnet_id
            )
            sg_ids = lt_data["NetworkInterfaces"][0]["Groups"]
            sg_names = []
            for sg_id in sg_ids:
                sg = ec2_client.describe_security_groups(GroupIds=[sg_id])
                sg_tags = sg["SecurityGroups"][0].get("Tags", [])
                sg_name = next(
                    (tag["Value"] for tag in sg_tags if tag["Key"] == "Name"), sg_id
                )
                    
                sg_names.append(sg_name)

            private_ips = [
                addr["PrivateIpAddress"]
                for nic in lt_data.get("NetworkInterfaces", [])
                for addr in nic.get("PrivateIpAddresses", [])
            ]

            ss_info = {
                "SourceServerName": source_instance_name,
                "OriginInstanceID": source_instance_id,
                "SourceServerID": ss_id,
                "CopyPrivateIP": lc["copyPrivateIp"],
                "CopyTags": lc["copyTags"],
                "TemplateID": lt_id,
                "TemplateVersion": default_lt_version,
                "LaunchState": lc["launchDisposition"],
                "Rightsizing": lc["targetInstanceTypeRightSizingMethod"],
                "InstanceType": instance_type,
                "SubnetName": subnet_name,
                "SubnetID": subnet_id,
                "PrivateIPs": ", ".join(private_ips),
                "SecurityGroupIDs": ", ".join(sg_ids),
                "SecurityGroupNames": ", ".join(sg_names),
            }
            
            ss_total_info.append(ss_info)

            for vol in lt_data["BlockDeviceMappings"]:
                ss_volumes.append(
                    {
                        "Hostname": source_instance_name,
                        "OriginInstanceID": source_instance_id,
                        "DeviceName": vol["DeviceName"],
                        "Type": vol["Ebs"]["VolumeType"],
                        "Size": vol["Ebs"]["VolumeSize"],
                        "IOPS": vol["Ebs"]["Iops"],
                        "Throughput": vol["Ebs"]["Throughput"],
                    }
                )

            ss_volumes = sorted(ss_volumes, key=lambda x: x["Size"])
            volumes.extend(ss_volumes)

            # Collect security group details
            for sg in sg_ids:
                sg_details = ec2_client.describe_security_groups(GroupIds=[sg_id])[
                    "SecurityGroups"
                ][0]
                sg_name = next(
                    (
                        tag["Value"]
                        for tag in sg_details.get("Tags", [])
                        if tag["Key"] == "Name"
                    ),
                    "",
                )

                # Process inbound rules
                for rule in sg_details["IpPermissions"]:
                    from_port = rule.get("FromPort", "All")
                    to_port = rule.get("ToPort", "All")
                    protocol = rule.get("IpProtocol", "All")

                    for ip_range in rule.get("IpRanges", []):
                        rule_description = ip_range.get("Description", " ")
                        security_rules.append(
                            {
                                "Hostname": source_instance_name,
                                "OriginInstanceID": source_instance_id,
                                "SecurityGroupName": sg_name,
                                "SecurityGroupID": sg_id,
                                "Direction": "Inbound",
                                "Protocol": protocol,
                                "FromPort": from_port,
                                "ToPort": to_port,
                                "CIDR": ip_range["CidrIp"],
                                "RuleDescription": rule_description,
                            }
                        )

                    for ip_range in rule.get("Ipv6Ranges", []):
                        rule_description = ip_range.get("Description", " ")
                        security_rules.append(
                            {
                                "Hostname": source_instance_name,
                                "OriginInstanceID": source_instance_id,
                                "SecurityGroupName": sg_name,
                                "SecurityGroupID": sg_id,
                                "Direction": "Inbound",
                                "Protocol": protocol,
                                "FromPort": from_port,
                                "ToPort": to_port,
                                "CIDR": ip_range["CidrIpv6"],
                                "RuleDescription": rule_description,
                            }
                        )

                    for prefix_list in rule.get("PrefixListIds", []):
                        rule_description = prefix_list.get("Description", " ")
                        security_rules.append(
                            {
                                "Hostname": source_instance_name,
                                "OriginInstanceID": source_instance_id,
                                "SecurityGroupName": sg_name,
                                "SecurityGroupID": sg_id,
                                "Direction": "Inbound",
                                "Protocol": protocol,
                                "FromPort": from_port,
                                "ToPort": to_port,
                                "CIDR": prefix_list["PrefixListId"],
                                "RuleDescription": rule_description,
                            }
                        )

                # Process outbound rules
                for rule in sg_details["IpPermissionsEgress"]:
                    from_port = rule.get("FromPort", "All")
                    to_port = rule.get("ToPort", "All")
                    protocol = rule.get("IpProtocol", "All")

                    for ip_range in rule.get("IpRanges", []):
                        rule_description = ip_range.get("Description", " ")
                        security_rules.append(
                            {
                                "Hostname": source_instance_name,
                                "OriginInstanceID": source_instance_id,
                                "SecurityGroupName": sg_name,
                                "SecurityGroupID": sg_id,
                                "Direction": "Outbound",
                                "Protocol": protocol,
                                "FromPort": from_port,
                                "ToPort": to_port,
                                "CIDR": ip_range["CidrIp"],
                                "RuleDescription": rule_description,
                            }
                        )

                    for ip_range in rule.get("Ipv6Ranges", []):
                        rule_description = ip_range.get("Description", " ")
                        security_rules.append(
                            {
                                "Hostname": source_instance_name,
                                "OriginInstanceID": source_instance_id,
                                "SecurityGroupName": sg_name,
                                "SecurityGroupID": sg_id,
                                "Direction": "Outbound",
                                "Protocol": protocol,
                                "FromPort": from_port,
                                "ToPort": to_port,
                                "CIDR": ip_range["CidrIpv6"],
                                "RuleDescription": rule_description,
                            }
                        )

                    for prefix_list in rule.get("PrefixListIds", []):
                        rule_description = prefix_list.get("Description", " ")
                        security_rules.append(
                            {
                                "Hostname": source_instance_name,
                                "OriginInstanceID": source_instance_id,
                                "SecurityGroupName": sg_name,
                                "SecurityGroupID": sg_id,
                                "Direction": "Outbound",
                                "Protocol": protocol,
                                "FromPort": from_port,
                                "ToPort": to_port,
                                "CIDR": prefix_list["PrefixListId"],
                                "RuleDescription": rule_description,
                            }
                        )

            ss_list.append(
                {
                    "Hostname": source_instance_name,
                    "SourceServerID": ss_id,
                    "OriginInstanceID": source_instance_id,
                    "OriginAccountID": ss["items"][0]["sourceCloudProperties"][
                        "originAccountID"
                    ],
                    "OriginRegion": ss["items"][0]["sourceCloudProperties"][
                        "originRegion"
                    ],
                }
            )

            logActions(
                "INF",
                f"successfully parsed info for source server {ss_id} ({source_instance_name})",
                None,
            )

        except Exception as e:
            logActions("ERR", f"Failed to parse info for source server {ss_id}", e)

    return ss_list, ss_total_info, volumes, security_rules


def update_workbook(
    source_server_list, drs_details, drs_vol_details, drs_sg_details, file_path
):
    """Updates the XLS doc with DRS related info

    :param source_server_list: Source server list
    :type source_server_list: list
    :param drs_details: DRS data
    :type drs_details: list
    :param drs_vol_details: Volume data
    :type drs_vol_details: list
    :param drs_sg_details: Security Group data
    :type drs_sg_details: list
    :param file_path: Path to the XLS doc
    :type file_path: string
    """
    
    try:
        # Convert to DataFrames
        ss_list_df = pd.DataFrame(source_server_list)
        ss_df = pd.DataFrame(drs_details)
        volumes_df = pd.DataFrame(drs_vol_details)
        rules_df = pd.DataFrame(drs_sg_details)

        # Save all DataFrames to Excel
        with pd.ExcelWriter(
            file_path, engine="openpyxl", mode="a", if_sheet_exists="replace"
        ) as writer:
            ss_list_df.to_excel(writer, sheet_name="List", index=False)
            ss_df.to_excel(writer, sheet_name="DRS_Details", index=False)
            volumes_df.to_excel(writer, sheet_name="DRS_Vol_Details", index=False)
            rules_df.to_excel(writer, sheet_name="DRS_SG_Details", index=False)

        logActions("INF", f"Successfully updated XLS document ({file_path})", None)
    except Exception as e:
        logActions("ERR", f"Failed to update XLS document ({file_path})", e)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--region", type=str, required=True, help="Name of the DR Region"
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
    list_df = read_excel(file_path)
    source_server_list, drs_details, drs_vol_details, drs_sg_details = get_drs_details(
        list_df, drs_client, ec2_client
    )
    update_workbook(
        source_server_list, drs_details, drs_vol_details, drs_sg_details, file_path
    )
    logActions("INF", f"Execution finished", None)
