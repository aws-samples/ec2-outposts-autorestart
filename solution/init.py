#!/usr/bin/env python3

import argparse
import boto3
import sys


def parse_arguments():
    parser = argparse.ArgumentParser(description='Deploy a CloudFormation stack to set up instance auto-restart on Outpost servers.')
    parser.add_argument('--launch-template-id', type=str, nargs='+', required=True, help='Launch template IDs')
    parser.add_argument('--source-outpost-id', type=str, required=True, help='Source Outpost ID')
    parser.add_argument('--template-file', type=str, required=True, help='Path to the CloudFormation template file')
    parser.add_argument('--stack-name', type=str, required=True, help='Name of the CloudFormation stack')
    parser.add_argument('--region', type=str, required=True, help='AWS region for the CloudFormation stack')
    parser.add_argument('--notification-email', type=str, required=True, help='Email address for SNS notifications')
    return parser.parse_args()


def prompt_descriptions(lt_ids, lt_id_type):
    descriptions = {}
    for lt in lt_ids:
        description = input(f"Enter a description for {lt_id_type} '{lt}': ")
        descriptions[lt] = description
    return descriptions


def prompt_stack_replacement(stack_name):
    response = input(f"The stack '{stack_name}' already exists. Do you want to replace it? (y/n): ")
    return response.strip().lower() == 'y'


def prompt_template_confirmation():
    response = input("Please confirm if the generated template looks good. (y/n): ")
    return response.strip().lower() == 'y'


def stack_exists(client, stack_name):
    try:
        client.describe_stacks(StackName=stack_name)
        return True
    except client.exceptions.ClientError:
        return False


def wait_for_stack(client, stack_name, action):
    waiter = client.get_waiter('stack_' + ('update_complete' if action == 'update' else 'create_complete'))
    print(f"Waiting for stack {action} to complete...")
    try:
        waiter.wait(StackName=stack_name)
        print(f"Stack {stack_name} has been {action}d successfully.")
    except Exception as e:
        print(f"An error occurred while waiting for the stack {action} to complete: {str(e)}")
        sys.exit(1)


def create_or_update_stack(client, stack_name, template_body, parameters):
    if stack_exists(client, stack_name):
        print(f"Stack {stack_name} exists. Updating stack...")
        response = client.update_stack(
            StackName=stack_name,
            TemplateBody=template_body,
            Parameters=parameters,
            Capabilities=['CAPABILITY_NAMED_IAM']
        )
        wait_for_stack(client, stack_name, 'update')
    else:
        print(f"Stack {stack_name} does not exist. Creating stack...")
        response = client.create_stack(
            StackName=stack_name,
            TemplateBody=template_body,
            Parameters=parameters,
            Capabilities=['CAPABILITY_NAMED_IAM']
        )
        wait_for_stack(client, stack_name, 'create')


def generate_template_body(base_template_path, launch_template_descriptions):
    with open(base_template_path, 'r') as file:
        template_body = file.read()

    outputs_lines = []

    for index, (template_id, description) in enumerate(launch_template_descriptions.items(), start=1):
        outputs_lines.extend([
            f"  LaunchTemplateId{index}:\n"
            f"    Description: \"{description}\"\n"
            f"    Value: \"{template_id}\"\n"
        ])
        outputs_section = ''.join(outputs_lines)

    template_body = template_body.replace("  # Outputs will be dynamically inserted here", outputs_section.rstrip())

    return template_body


def main():
    args = parse_arguments()

    launch_template_descriptions = prompt_descriptions(args.launch_template_id, "launch template ID")

    print("Descriptions provided for launch templates:")
    for template_id, description in launch_template_descriptions.items():
        print(f"{template_id}: {description}")

    client = boto3.client('cloudformation', region_name=args.region)

    if stack_exists(client, args.stack_name) and not prompt_stack_replacement(args.stack_name):
        print("Operation cancelled by user.")
        sys.exit(0)

    template_body = generate_template_body(args.template_file, launch_template_descriptions)

    print("Generated CloudFormation Template:")
    print(template_body)

    if not prompt_template_confirmation():
        print("Operation cancelled by user.")
        sys.exit(0)

    parameters = [
        {
            'ParameterKey': 'StackName',
            'ParameterValue': args.stack_name
        },
        {
            'ParameterKey': 'SourceOutpostId',
            'ParameterValue': args.source_outpost_id
        },
        {
            'ParameterKey': 'NotificationEmail',
            'ParameterValue': args.notification_email
        }
    ]

    create_or_update_stack(client, args.stack_name, template_body, parameters)


if __name__ == "__main__":
    main()
