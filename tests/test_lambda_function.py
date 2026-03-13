import os
import sys
import datetime
from importlib import reload
from unittest.mock import patch, MagicMock

import boto3
import pytest
from botocore.exceptions import ClientError
from moto import mock_aws

# Add the src directory to the module path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../src')))

@pytest.fixture(scope="function", autouse=True)
def aws_credentials():
    """Mocked AWS Credentials for moto."""
    os.environ['AWS_ACCESS_KEY_ID'] = 'testing'
    os.environ['AWS_SECRET_ACCESS_KEY'] = 'testing'
    os.environ['AWS_SECURITY_TOKEN'] = 'testing'
    os.environ['AWS_SESSION_TOKEN'] = 'testing'
    os.environ['AWS_DEFAULT_REGION'] = 'us-west-2'

@pytest.fixture(scope="function")
def ec2_client():
    with mock_aws():
        yield boto3.client('ec2', region_name='us-west-2')

@pytest.fixture(scope="function")
def lambda_context():
    context = MagicMock()
    context.function_name = "test-function"
    return context

@pytest.fixture(scope="function")
def clean_lambda():
    import lambda_function
    return reload(lambda_function)

def test_lambda_handler_deletes_old_snapshot(ec2_client, lambda_context, clean_lambda):
    # 1. Setup: Create a snapshot
    vol_res = ec2_client.create_volume(AvailabilityZone='us-west-2a', Size=10)
    vol_id = vol_res['VolumeId']
    snap_res = ec2_client.create_snapshot(VolumeId=vol_id, Description="Old snapshot")
    snap_id = snap_res['SnapshotId']

    # Delete volume so snapshot isn't in use
    ec2_client.delete_volume(VolumeId=vol_id)

    # 2. Mock datetime
    future_date = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(days=400)
    
    with patch('lambda_function.datetime') as mock_datetime:
        mock_datetime.datetime.now.return_value = future_date
        mock_datetime.timezone = datetime.timezone
        mock_datetime.timedelta = datetime.timedelta
        
        with patch('lambda_function.get_ec2_client') as mock_get_client:
            mock_get_client.return_value = ec2_client
            response = clean_lambda.lambda_handler({}, lambda_context)

    # Assertions
    assert response['statusCode'] == 200

    # Verify our specific snapshot is gone
    snaps = ec2_client.describe_snapshots(OwnerIds=['self'])['Snapshots']
    snapshot_ids = [s['SnapshotId'] for s in snaps]
    assert snap_id not in snapshot_ids

def test_lambda_handler_skips_recent_snapshot(ec2_client, lambda_context, clean_lambda):
    # Setup: Create a snapshot
    vol_res = ec2_client.create_volume(AvailabilityZone='us-west-2a', Size=10)
    vol_id = vol_res['VolumeId']
    snap_res = ec2_client.create_snapshot(VolumeId=vol_id, Description="Recent snapshot")
    snap_id = snap_res['SnapshotId']
    
    ec2_client.delete_volume(VolumeId=vol_id)

    with patch('lambda_function.get_ec2_client') as mock_get_client:
        mock_get_client.return_value = ec2_client
        response = clean_lambda.lambda_handler({}, lambda_context)

    # Assertions
    assert response['statusCode'] == 200

    # Verify our specific snapshot still exists
    snaps = ec2_client.describe_snapshots(OwnerIds=['self'])['Snapshots']
    snapshot_ids = [s['SnapshotId'] for s in snaps]
    assert snap_id in snapshot_ids

def test_lambda_handler_deletes_snapshot_with_derived_volume(ec2_client, lambda_context, clean_lambda):
    # A volume exists that was created from this snapshot, but the snapshot is not
    # backing an AMI. The snapshot is therefore orphaned and should be deleted —
    # the volume is a full independent copy and is unaffected by snapshot deletion.
    base_vol = ec2_client.create_volume(AvailabilityZone='us-west-2a', Size=10)
    snap_res = ec2_client.create_snapshot(VolumeId=base_vol['VolumeId'], Description="Orphaned snapshot")
    snap_id = snap_res['SnapshotId']

    new_vol = ec2_client.create_volume(AvailabilityZone='us-west-2a', Size=10, SnapshotId=snap_id)
    new_vol_id = new_vol['VolumeId']

    instances = ec2_client.run_instances(
        ImageId='ami-12c6146b',
        MinCount=1,
        MaxCount=1,
        InstanceType='t2.micro',
        Placement={'AvailabilityZone': 'us-west-2a'}
    )
    instance_id = instances['Instances'][0]['InstanceId']

    ec2_client.attach_volume(
        Device='/dev/sdh',
        InstanceId=instance_id,
        VolumeId=new_vol_id
    )

    future_date = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(days=400)

    with patch('lambda_function.datetime') as mock_datetime:
        mock_datetime.datetime.now.return_value = future_date
        mock_datetime.timezone = datetime.timezone
        mock_datetime.timedelta = datetime.timedelta

        with patch('lambda_function.get_ec2_client') as mock_get_client:
            mock_get_client.return_value = ec2_client
            response = clean_lambda.lambda_handler({}, lambda_context)

    assert response['statusCode'] == 200

    # Snapshot should be deleted — derived volume is independent
    snaps = ec2_client.describe_snapshots(OwnerIds=['self'])['Snapshots']
    snapshot_ids = [s['SnapshotId'] for s in snaps]
    assert snap_id not in snapshot_ids


def test_lambda_handler_skips_ami_backed_snapshot(ec2_client, lambda_context, clean_lambda):
    # Create a snapshot and mock describe_images to report it as backing an AMI.
    # moto's register_image does not reliably populate SnapshotId in describe_images
    # results, so we mock the response directly to exercise the lambda code path.
    vol_res = ec2_client.create_volume(AvailabilityZone='us-west-2a', Size=10)
    snap_res = ec2_client.create_snapshot(VolumeId=vol_res['VolumeId'], Description="AMI-backed snapshot")
    snap_id = snap_res['SnapshotId']

    ami_page = {
        'Images': [
            {
                'ImageId': 'ami-12345678',
                'BlockDeviceMappings': [
                    {'DeviceName': '/dev/sda1', 'Ebs': {'SnapshotId': snap_id}},
                ],
            }
        ]
    }

    # Patch only the describe_images paginator; let describe_instances and
    # describe_snapshots run normally through moto.
    real_get_paginator = ec2_client.get_paginator

    def selective_paginator(operation):
        if operation == 'describe_images':
            mock_pag = MagicMock()
            mock_pag.paginate.return_value = [ami_page]
            return mock_pag
        return real_get_paginator(operation)

    future_date = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(days=400)

    with patch('lambda_function.datetime') as mock_datetime:
        mock_datetime.datetime.now.return_value = future_date
        mock_datetime.timezone = datetime.timezone
        mock_datetime.timedelta = datetime.timedelta

        with patch('lambda_function.get_ec2_client') as mock_get_client:
            mock_get_client.return_value = ec2_client
            with patch.object(ec2_client, 'get_paginator', side_effect=selective_paginator):
                response = clean_lambda.lambda_handler({}, lambda_context)

    assert response['statusCode'] == 200

    snaps = ec2_client.describe_snapshots(OwnerIds=['self'])['Snapshots']
    snapshot_ids = [s['SnapshotId'] for s in snaps]
    assert snap_id in snapshot_ids


def _client_error(code):
    return ClientError({'Error': {'Code': code, 'Message': 'test'}}, 'DeleteSnapshot')


def test_lambda_handler_handles_api_in_use_error(ec2_client, lambda_context, clean_lambda):
    # Snapshot passes the pre-flight check (no attached volume, no AMI) but
    # the API returns InvalidSnapshot.InUse — exercises the except fallback path.
    vol_res = ec2_client.create_volume(AvailabilityZone='us-west-2a', Size=10)
    snap_res = ec2_client.create_snapshot(VolumeId=vol_res['VolumeId'], Description="API in-use snapshot")
    ec2_client.delete_volume(VolumeId=vol_res['VolumeId'])

    future_date = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(days=400)

    with patch('lambda_function.datetime') as mock_datetime:
        mock_datetime.datetime.now.return_value = future_date
        mock_datetime.timezone = datetime.timezone
        mock_datetime.timedelta = datetime.timedelta

        with patch('lambda_function.get_ec2_client') as mock_get_client:
            mock_get_client.return_value = ec2_client
            with patch.object(ec2_client, 'delete_snapshot',
                              side_effect=_client_error('InvalidSnapshot.InUse')):
                response = clean_lambda.lambda_handler({}, lambda_context)

    assert response['statusCode'] == 200


def test_lambda_handler_logs_error_on_unexpected_delete_failure(ec2_client, lambda_context, clean_lambda):
    # delete_snapshot raises an unexpected ClientError — exercises the logger.error path.
    vol_res = ec2_client.create_volume(AvailabilityZone='us-west-2a', Size=10)
    snap_res = ec2_client.create_snapshot(VolumeId=vol_res['VolumeId'], Description="Error snapshot")
    snap_id = snap_res['SnapshotId']
    ec2_client.delete_volume(VolumeId=vol_res['VolumeId'])

    future_date = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(days=400)

    with patch('lambda_function.datetime') as mock_datetime:
        mock_datetime.datetime.now.return_value = future_date
        mock_datetime.timezone = datetime.timezone
        mock_datetime.timedelta = datetime.timedelta

        with patch('lambda_function.get_ec2_client') as mock_get_client:
            mock_get_client.return_value = ec2_client
            with patch.object(ec2_client, 'delete_snapshot',
                              side_effect=_client_error('UnauthorizedOperation')):
                with patch.object(clean_lambda.logger, 'error') as mock_error:
                    response = clean_lambda.lambda_handler({}, lambda_context)

    assert response['statusCode'] == 200
    assert mock_error.called
    assert any(snap_id in str(call) for call in mock_error.call_args_list)