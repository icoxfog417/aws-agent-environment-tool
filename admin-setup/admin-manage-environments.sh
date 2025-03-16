#!/bin/bash

# Script for administrators to manage development environments

function list_environments() {
  echo "Listing all development environments:"
  aws ec2 describe-instances \
    --filters "Name=tag:ManagedBy,Values=SSM-ApplicationManager" \
    --query "Reservations[].Instances[].{InstanceId:InstanceId,Developer:Tags[?Key=='Developer']|[0].Value,State:State.Name,LaunchTime:LaunchTime}" \
    --output table
}

function stop_inactive_environments() {
  echo "Stopping environments that have been idle for more than 12 hours..."
  # This would require additional logic to check CloudWatch metrics for activity
  # For simplicity, we'll just list environments that could be stopped
  aws ec2 describe-instances \
    --filters "Name=tag:ManagedBy,Values=SSM-ApplicationManager" "Name=instance-state-name,Values=running" \
    --query "Reservations[].Instances[].{InstanceId:InstanceId,Developer:Tags[?Key=='Developer']|[0].Value,LaunchTime:LaunchTime}" \
    --output table
  
  read -p "Enter instance IDs to stop (comma-separated) or press Enter to skip: " INSTANCE_IDS
  
  if [ ! -z "$INSTANCE_IDS" ]; then
    IFS=',' read -ra INSTANCES <<< "$INSTANCE_IDS"
    for INSTANCE in "${INSTANCES[@]}"; do
      INSTANCE=$(echo $INSTANCE | xargs)  # Trim whitespace
      echo "Stopping instance $INSTANCE..."
      aws ec2 stop-instances --instance-ids $INSTANCE
    done
  fi
}

function update_all_environments() {
  echo "Triggering SSM patch management on all environments..."
  aws ssm start-automation-execution \
    --document-name "AWS-RunPatchBaseline" \
    --targets "Key=tag:ManagedBy,Values=SSM-ApplicationManager" \
    --target-parameter-name "InstanceId"
}

function show_usage() {
  echo "Usage: $0 [list|stop-inactive|update-all]"
  echo "  list           - List all development environments"
  echo "  stop-inactive  - Stop environments that have been idle"
  echo "  update-all     - Run updates on all environments"
}

# Main script
case "$1" in
  list)
    list_environments
    ;;
  stop-inactive)
    stop_inactive_environments
    ;;
  update-all)
    update_all_environments
    ;;
  *)
    show_usage
    ;;
esac
