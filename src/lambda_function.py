import boto3
import datetime
import logging
from botocore.exceptions import ClientError

# Set up logging
logger = logging.getLogger()
logger.setLevel(logging.INFO)

def get_ec2_client():
    return boto3.client('ec2')

def lambda_handler(event, context):
    ec2_client = get_ec2_client()
    try:
        # 1. Calculate the cutoff date (1 year ago)
        cutoff_date = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=365)
        logger.info(f"Looking for snapshots older than: {cutoff_date}")

        # 2. Gather Context (Safety Check) - Find snapshots backing a registered AMI.
        # These are the only snapshots that are truly "in use" — AWS will block their
        # deletion with InvalidSnapshot.InUse. All other old snapshots are safe to delete.
        in_use_snapshot_ids = set()

        logger.info("Gathering AMIs owned by account...")
        paginator_images = ec2_client.get_paginator('describe_images')
        for page in paginator_images.paginate(Owners=['self']):
            for image in page.get('Images', []):
                for block_device in image.get('BlockDeviceMappings', []):
                    if 'Ebs' in block_device and 'SnapshotId' in block_device['Ebs']:
                        in_use_snapshot_ids.add(block_device['Ebs']['SnapshotId'])

        # 3. Retrieve all custom snapshots
        logger.info("Retrieving all self-owned snapshots...")
        paginator_snapshots = ec2_client.get_paginator('describe_snapshots')
        
        evaluated_count = 0
        deleted_count = 0
        skipped_in_use_count = 0
        skipped_recent_count = 0

        for page in paginator_snapshots.paginate(OwnerIds=['self']):
            for snapshot in page['Snapshots']:
                snapshot_id = snapshot['SnapshotId']
                start_time = snapshot['StartTime']
                evaluated_count += 1

                if start_time < cutoff_date:
                    if snapshot_id in in_use_snapshot_ids:
                        logger.info(f"Snapshot {snapshot_id} is older than 1 year but is IN USE. Skipping deletion.")
                        skipped_in_use_count += 1
                    else:
                        logger.info(f"Attempting to delete snapshot: {snapshot_id}")
                        try:
                            ec2_client.delete_snapshot(SnapshotId=snapshot_id)
                            logger.info(f"Successfully deleted snapshot: {snapshot_id}")
                            deleted_count += 1
                        except ClientError as e:
                            if e.response['Error']['Code'] == 'InvalidSnapshot.InUse':
                                logger.info(f"Snapshot {snapshot_id} is in use (caught by AWS API).")
                                skipped_in_use_count += 1
                            else:
                                logger.error(f"Failed to delete {snapshot_id}: {e}")
                else:
                    skipped_recent_count += 1

        return {
            'statusCode': 200,
            'body': f"Evaluated: {evaluated_count}, Deleted: {deleted_count}, Skipped (in-use): {skipped_in_use_count}, Skipped (recent): {skipped_recent_count}"
        }

    except Exception as e:
        logger.error(f"An unexpected error occurred: {e}")
        raise
