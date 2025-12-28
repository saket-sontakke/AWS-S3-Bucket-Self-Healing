#!/usr/bin/env python3
import boto3
import json
import time
import argparse
from statistics import mean

def parse_args():
    p = argparse.ArgumentParser(description="Iteratively disable S3 Block Public Access and invoke remediation lambda")
    p.add_argument("--bucket", required=True, help="secure-self-healing-bucket")
    p.add_argument("--function", required=True, help="S3BucketSelfHeal")
    p.add_argument("--iterations", type=int, default=50, help="Number of iterations (default: 50)")
    p.add_argument("--region", default=None, help="eu-north-1")
    return p.parse_args()

def disable_block_public(bucket, s3):
    s3.put_public_access_block(
        Bucket=bucket,
        PublicAccessBlockConfiguration={
            'BlockPublicAcls': False,
            'IgnorePublicAcls': False,
            'BlockPublicPolicy': False,
            'RestrictPublicBuckets': False
        }
    )

def enable_block_public(bucket, s3):
    s3.put_public_access_block(
        Bucket=bucket,
        PublicAccessBlockConfiguration={
            'BlockPublicAcls': True,
            'IgnorePublicAcls': True,
            'BlockPublicPolicy': True,
            'RestrictPublicBuckets': True
        }
    )

def invoke_remediation(bucket, function_name, lambda_client):
    event = {"resources": [f"arn:aws:s3:::{bucket}"]}
    start = time.time()
    resp = lambda_client.invoke(
        FunctionName=function_name,
        InvocationType="RequestResponse",
        Payload=json.dumps(event)
    )
    body = json.loads(resp["Payload"].read().decode())
    end = time.time()
    # assume your lambda payload returns its own timing under 'response_time_ms'
    lambda_time = body.get("response_time_ms", None)
    client_time = int((end - start) * 1000)
    return client_time, lambda_time

def main():
    args = parse_args()
    session = boto3.Session(region_name=args.region) if args.region else boto3.Session()
    s3 = session.client("s3")
    lam = session.client("lambda")

    client_times = []
    lambda_times = []

    for i in range(args.iterations):
        print(f"Iteration {i+1}/{args.iterations} – disabling block public access…")
        disable_block_public(args.bucket, s3)

        print("Invoking remediation lambda…")
        client_ms, lambda_ms = invoke_remediation(args.bucket, args.function, lam)
        client_times.append(client_ms)
        if lambda_ms is not None:
            lambda_times.append(lambda_ms)
            print(f" → client RTT: {client_ms} ms, lambda reported: {lambda_ms} ms")
        else:
            print(f" → client RTT: {client_ms} ms, lambda timing not returned")

        print("Re‑enabling block public access…\n")
        enable_block_public(args.bucket, s3)

        # small pause to let everything settle
        time.sleep(1)

    print("=== RESULTS ===")
    print(f"Client-side RTT over {len(client_times)} runs: avg = {mean(client_times):.2f} ms")
    if lambda_times:
        print(f"Lambda‑reported response time over {len(lambda_times)} runs: avg = {mean(lambda_times):.2f} ms")

if __name__ == "__main__":
    main()
