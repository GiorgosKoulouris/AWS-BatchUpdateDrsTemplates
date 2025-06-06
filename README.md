# AWS - Bulk modify DRS Launch Templates

## Overview

### Code documentation

Detailed script documentation can be found
<a href="https://giorgoskoulouris.github.io/AWS-BatchUpdateDrsTemplates/" target="_blank">here</a>.


### High level info
The following process facilitates batch updates of the launch configuration and launch templates of DRS servers. Data is stored and validated on an XLS spreadsheet. This is to enable manual edits and data consistency when the scripts are executed on different shells/environments.

### Execution steps

- List all source servers (DR Account/Region)
- Modify the list of the source servers you want to target (Open and edit the XLS)
- Parse current DRS launch configuration and templates for the targeted servers (DR Account/Region)
- Parse all needed information from the respective (replicated) instances (Prod Account/Region) (optional)
- Create (or update) the XLS worksheets that hold the data for the modifications
- Modify the launch configuration and templates (DR Account/Region)

## Detailed steps

### Initialize environment
Initialize a python environment. This is to avoid installing modules on the broader environment.

```bash
python3 -m venv venv
source ./venv/bin/activate
python -m pip install boto3 pandas openpyxl
```

### Get the complete source server list
This will parse the complete source server list and will initialize/create the XLS document. Create a file named *init_xls.py* and paste the content of the corresponding file. Then execute the script.

```bash
wget https://tcop-github-repos.s3.eu-central-1.amazonaws.com/AWS-BatchUpdateDrsTemplates/init_xls.py
python init_xls.py --region regionName --workbook-path ./DRS_Templates.xlsx
```

**NOTE:** If the *--workbook-path* option is omitted, by default, the XLS file will be placed in your working directory and will be named *DRS_Templates.xlsx*


### Modify the targeted source server configurations
Open the XLS file and edit the list of the servers you want to modify the configuration for. A sheet named *All_Servers* contains the full list of the servers. The sheet *List* is the one you need to modify. Remove any servers you dont want edit/modify during the process. By removing servers, large environments can be separated into smaller batches.

**NOTE:** The script overwrites the XLS document in various steps, keep a backup of the document between executions.

### Parse the current DRS configuration
This action will update the XLS document with all information related with the configuration of the source servers.

On the DR Account/Region, make sure that the latest version of the XLS document is available. Create a file named *parse_drs_info.py* and paste the content of the corresponding file. Then execute the script.

```bash
wget https://tcop-github-repos.s3.eu-central-1.amazonaws.com/AWS-BatchUpdateDrsTemplates/parse_drs_info.py
python parse_drs_info.py --region regionName --workbook-path ./DRS_Templates.xlsx
```

**NOTE:** If the *--workbook-path* option is omitted, the default XLS file path is *./DRS_Templates.xlsx*

### Parse the information related with the replicated instances

**NOTE:** This step is optional, however executing this and updating the XLS doc is useful to compare PROD and DR configurations side-by-side.

On the Prod Account/Region, make sure that the latest version of the XLS document is available. Create a file named *parse_ec2_info.py* and paste the content of the corresponding file. Then execute the script.

```bash
wget https://tcop-github-repos.s3.eu-central-1.amazonaws.com/AWS-BatchUpdateDrsTemplates/parse_ec2_info.py
python parse_ec2_info.py --region regionName --workbook-path ./DRS_Templates.xlsx
```

This action will update the XLS document with all information related the configuration of actual replicated EC2 instances.

**NOTE:** If the *--workbook-path* option is omitted, the default XLS file path is *./DRS_Templates.xlsx*

### Create (or update) the modification XLS worksheets
This action will create the necessary sheets that contain side-by-side information regarding the configuration of the replicated EC2 instances and the DRS servers.

This step can be executed on any environment, the only thing needed is the latest XLS document version. Create a file named *create_mod_sheets.py* and paste the content of the corresponding file. Then execute the script.

**NOTE:** This step needs to be executed every time you either execute *parse_drs_info.py* or *parse_ec2_info.py*

```bash
wget https://tcop-github-repos.s3.eu-central-1.amazonaws.com/AWS-BatchUpdateDrsTemplates/create_mod_sheets.py
python create_mod_sheets.py --workbook-path ./DRS_Templates.xlsx
```

**NOTE:** If the *--workbook-path* option is omitted, the default XLS file path is *./DRS_Templates.xlsx*

### Review and update the XLS with the new configuration
Open and edit the XLS document accordingly. The 2 sheets that you need to review and/or modify are **Mod_TemplateConfigs** and **Mod_VolumeConfigs**.

On each sheet there is a set of options. Each option has 3 collumns related with it *EC2_OptionName*, *DRS_OptionName* and *New_OptionName*. Some options that do not have an equivalent on EC2, have just 2 collumns: *DRS_OptionName* and *New_OptionName*.

For each option you need to modify, enter the respective value on the cell under the *New_OptionName* collumn.

#### Notes on values
- **Mod_TemplateConfigs**
    - **New_LaunchState:** Launch state when the recovery instance is launched. Valid values: **STARTED** and **STOPPED**
    - **New_DrsSubnetID:** The DR subnet to launch the recovery instance in
    - **New_CopyPrivateIP:** Whether DRS will copy the primary IP of the replicated instance. Valid values: **TRUE** and **FALSE**
    - **New_PrivateIPs:** Private IP of the launched instance. Add a comma-separated list if you need to add secondary IPs on the primary interface
    - **New_RightSizing:** Whether DRS will modify the launch template to match the instance type of the replicated instance. Valid values: **TRUE** and **FALSE**
    - **New_InstanceType:** Custom instance type for the launched recovery instance
    - **New_SecurityGroupIDs:** The security groups that will be attached to the recovery instance. Can be a comma-separated list for mutliple groups

- **Mod_VolumeConfigs**
    - **New_Type:** Type of the volume of the recovery instance
    - **New_IOPS:** Custom IOPS value for the volume of the recovery instance
    - **New_Throughput:** Custom Throughput value for the volume of the recovery instance

- **Cell Values:** Not all cell values will trigger a change. Empty cells mean no change. Also, cells on the *New_OptionName* collumn that have the same value with the respective *DRS_OptionName* mean no change.

**NOTE:** Volume mapping between the DRS launch tepmlates and the information parsed from EC2 cannot be determined with confidence. There is a risk that the XLS mapping will not be accurate. Always rule out inconsistennies by checking the size reported for each disk on DRS and EC2 collumns. Volume options are mostly helpfull if you need to batch update launch templates to default IOPS/Throughput due to an initial misconfiguration of the default template of the DRS service. As a best practice, after verifying the changes, delete your values from the *New_OptionName* collumns for the disks in order to avoid unecessary condifuration updates.

### Perform the actual modification
This step will perform the actual updates on the launch templates and launch configuration for each source server.

On the DR Account/Region, make sure that the latest version of the XLS document is available. Create a file named *modify_launch_templates.py* and paste the content of the corresponding file. Then execute the script.

```bash
wget https://tcop-github-repos.s3.eu-central-1.amazonaws.com/AWS-BatchUpdateDrsTemplates/modify_launch_templates.py
python modify_launch_templates.py --region regionName --workbook-path ./DRS_Templates.xlsx
```

**NOTE:** If the *--workbook-path* option is omitted, the default XLS file path is *./DRS_Templates.xlsx*

#### Execution details
- Checks for any changes between the current and the target config
- Modifies the target object as per the found changes (launch configuration and launch template)
    - Empty cells are ignored
    - Cells that contain the same value as the current configuration are ignored
- If the launch configuration was modified, an update will be submitted for the source server
- If the launch template was modified, a new version of the template will be created and will become the default one
- If even one of the source servers had its launch configuration or launch template modified, the script parses the updated data from DRS again and recreates the modification sheets in the XLS documented. Custom values on the *New_OptionName* collumns are not overwritten. If the original modification was successful, a subsequent execution of the script should bring no more changes.

## Worksheet details
This is a short description of each sheet created by the scripts.

- **All_Servers**: Contains all source servers that are configured for DRS 
- **List**: The list of the servers you want to modify the DRS configuration for. After running *init_xls.py*, remove any lines for the servers you don't want to reconfigure
- **DRS_Details**: Contains all information related to DRS configuration. Gets updated when *parse_drs_info.py* is executed, or when DRS configuration gets modified
- **DRS_Vol_Details**: Contains all information related to DRS volume configuration on the launch templates. Gets updated when *parse_drs_info.py* is executed, or when DRS configuration gets modified
- **DRS_SG_Details**: Contains all information related to DRS Security Group configuration on the launch templates. Gets updated when *parse_drs_info.py* is executed, or when DRS configuration gets modified
- **Initial_DRS_Details**: Contains initial information related to DRS configuration. Gets updated only when *parse_drs_info.py* is executed. This is to have a reference of the configuration before applying any modifications
- **Initial_DRS_Vol_Details**: Contains initial information related to DRS volume configuration on the launch templates. Gets updated only when *parse_drs_info.py* is executed. This is to have a reference of the configuration before applying any modifications
- **EC2_Details**: Contains all information related to the configuration of the live EC2 instances. Gets updated when *parse_ec2_info.py* is executed
- **EC2_SG_Details**: Contains all information related to the configuration of the Security Groups of the live EC2 instances. Gets updated when *parse_ec2_info.py* is executed
- **EC2_Vol_Details**: Contains all information related to the volumes of the live EC2 instances. Gets updated when *parse_ec2_info.py* is executed
- **EC2_Tag_Details**: Contains all information related to the tags of the live EC2 instances. Gets updated when *parse_ec2_info.py* is executed
- **Mod_TemplateConfigs**: Contains a comparison between Prod and DR information. Also contains the modifications that will be applied when *modify_launch_templates.py* will be executed.
- **Mod_VolumeConfigs**: Contains a comparison between Prod and DR volume information. Also contains the volume-related modifications that will be applied when *modify_launch_templates.py* will be executed.
Mod_VolumeConfigs
- **DRS_Diff**: Contains side by side info about the initial DRS configuration (before any modifications) and the latest state. Gets updated when *modify_launch_templates.py* is executed
- **DRS_Volume_Diff**: Contains side by side info about the initial DRS volume configuration (before any modifications) and the latest state. Gets updated when *modify_launch_templates.py* is executed
