import os
import json
import time
import subprocess
import requests
import argparse
import urllib.parse
from dotenv import load_dotenv
from google.cloud import pubsub_v1
from datetime import datetime

def parse_args():
    """Parse command line arguments"""
    parser = argparse.ArgumentParser(description='Setup Orbit services and configuration')
    
    # Add mutually exclusive group for config source
    config_group = parser.add_mutually_exclusive_group()
    config_group.add_argument('--config', type=str, help='Path to config.json file')
    config_group.add_argument('--api-key', help='API Key for authentication')
    
    # Database connection group - either URI or individual parameters
    db_group = parser.add_mutually_exclusive_group()
    db_group.add_argument('--db-connection-uri', help='Database connection URI')
    db_group.add_argument('--db-host', help='Database host')
    parser.add_argument('--db-port', type=int, default=5432, help='Database port (default: 5432)')
    parser.add_argument('--db-name', help='Database name')
    parser.add_argument('--db-user', help='Database username')
    parser.add_argument('--db-password', help='Database password')
    
    # Agent configuration
    parser.add_argument('--agent-name', help='Name of the agent')
    parser.add_argument('--agent-description', help='Description of the agent')
    parser.add_argument('--jwt-token', help='JWT token for authentication')
    
    args = parser.parse_args()
    
    # If config file is provided, load and validate it
    if args.config:
        try:
            with open(args.config, 'r') as f:
                config = json.load(f)
            
            # Extract values from config
            args.data = config
            args.api_key = args.data.get('api_key')
            data = args.data.get('data', {})
            
            # Extract JWT token and orbit configuration
            args.jwt_token = data.get('jwt_token')
            
            # Extract orbit configuration
            orbit_config = data.get('orbit_configuration', {})
            args.db_connection_uri = orbit_config.get('connection_string')
            
            db_conn = orbit_config.get('db_connection')
            if db_conn:
                args.db_host = db_conn.get('host')
                args.db_port = db_conn.get('port')
                args.db_name = db_conn.get('database')
                args.db_user = db_conn.get('username')
                args.db_password = db_conn.get('password')
            
            # Extract agent configuration
            agent = data.get('agent', {})
            args.agent_name = agent.get('agent_name')
            args.agent_description = agent.get('agent_description')
            
            # Validate required fields based on process type
            if args.data.get("process_type") == "initial_provisioning_orbit":
                if not args.api_key:
                    raise ValueError("API key is required for initial_provisioning_orbit")
            elif args.data.get("process_type") == "create_agent_orbit":
                # API key not required for agent creation
                pass
            else:
                # For any other process type or when process_type is not specified
                if not args.api_key:
                    raise ValueError("API key is required when process_type is not specified")
                    
            if not (args.db_connection_uri or (db_conn and all([args.db_host, args.db_name, args.db_user, args.db_password]))):
                raise ValueError("Missing database configuration. Provide either connection_string or db_connection details")
                
        except (json.JSONDecodeError, FileNotFoundError) as e:
            raise ValueError(f"Error reading config file: {e}")
    
    # When not using config file
    else:
        # Set default process type and data structure
        args.data = {
            "process_type": "create_agent_orbit",  # Default to agent creation
            "process_id": None,
            "step_order": 0
        }
        
        # Validate database configuration
        if not args.db_connection_uri and not all([args.db_host, args.db_name, args.db_user, args.db_password]):
            raise ValueError("When not using --config or --db-connection-uri, you must specify --db-host, --db-name, --db-user, and --db-password")
    
    return args

def build_connection_uri(args):
    """Build database connection URI from individual parameters"""
    if args.db_connection_uri:
        return args.db_connection_uri
        
    # Validate required parameters when using individual connection details
    if not all([args.db_host, args.db_name, args.db_user, args.db_password]):
        raise ValueError("When not using --db-connection-uri, you must specify --db-host, --db-name, --db-user, and --db-password")
    
    # Build connection URI
    password = urllib.parse.quote_plus(args.db_password)  # URL encode the password
    return f"postgresql://{args.db_user}:{password}@{args.db_host}:{args.db_port}/{args.db_name}"

def run_docker_compose(api_key, args):
    """Deploy KAI and orbit worker services using docker-compose"""
    try:
        # Create the required Docker network if it doesn't exist
        try:
            subprocess.run(['docker', 'network', 'create', 'agentic_network'], check=True)
            print("Docker network 'agentic_network' created successfully")
        except subprocess.CalledProcessError:
            # Network might already exist, which is fine
            pass

        # Update .env.orbit file with the provided API key
        env_orbit_path = os.path.join(
            os.path.dirname(os.path.abspath(__file__)),
            'docker',
            '.env.orbit'
        )
        
        # Read existing content
        with open(env_orbit_path, 'r') as f:
            lines = f.readlines()
            
        # Update the API key line
        with open(env_orbit_path, 'w') as f:
            for line in lines:
                if line.startswith('ORBIT_API_KEY='):
                    f.write(f'ORBIT_API_KEY={api_key}\n')
                else:
                    f.write(line)
        
        subprocess.run(['docker-compose', '-f', 'docker/docker-compose.yml', 'up', '-d'], check=True)
        print("Docker services started successfully")
        # Give services some time to start up
        time.sleep(10)

        if args.data["process_id"]:
            # Create a new process in the KAI service
            args.data['step_order'] += 1
            process_payload = {
                "process_id": args.data['process_id'],
                "step": "Docker compose services started",
                "step_order": args.data['step_order'],
                "message": "KAI service and orbit worker services started successfully",
                "modified_at": datetime.now().isoformat()
            }
            response = requests.post(
                "http://localhost:8000/api/v1/provision/orbit/notification",
                headers={
                    "Authorization": args.jwt_token,
                    "Content-Type": "application/json"
                },
                json=process_payload
            )
            response.raise_for_status()
            print("Notification sent to main service")
        else:
            pass

    except subprocess.CalledProcessError as e:
        print(f"Error starting docker services: {e}")
        raise
    except IOError as e:
        print(f"Error updating .env.orbit file: {e}")
        raise



def configure_kai_service(connection_uri, args):
    """Configure KAI service with database connections and schemas"""
    # Load environment variables
    kai_address = "http://localhost:8005"
    
    try:
        print("Configuring KAI service...")
        print("Createing database connection...")
        # Step 1: Create database connection
        connection_payload = {
            "alias": "orbit",
            "connection_uri": connection_uri
        }
        print(f"Connection URI: {connection_uri}")
        response = requests.post(
            f"{kai_address}/api/v1/database-connections",
            json=connection_payload
        )
        response.raise_for_status()
        db_connection_id = response.json().get('id')
        
        print(f"Database connection created with ID: {db_connection_id}")
        print("Refreshing database...")
        # Step 2: Refresh database
        response = requests.post(
            f"{kai_address}/api/v1/table-descriptions/refresh",
            params={"database_connection_id": db_connection_id}
        )
        response.raise_for_status()
        table_descriptions = response.json()
        print(f"Table descriptions refreshed: {len(table_descriptions)} tables found")
        print("Configuring schemas...")
        # Step 3: Sync schemas
        table_description_ids = [desc['id'] for desc in table_descriptions]
        sync_payload = {
            "table_description_ids": table_description_ids,
            "instruction": "",
            "llm_config": {
                "model-family": "google",
                "model-name": "gemini-2.0-flash"
            }
        }
        response = requests.post(
            f"{kai_address}/api/v1/table-descriptions/sync-schemas",
            json=sync_payload
        )
        response.raise_for_status()
        print("KAI service configured successfully")

        if args.data['process_id']:
            # Create a new process in the KAI service
            args.data["step_order"] += 1
            process_payload = {
                "process_id": args.data['process_id'],
                "step": "KAI service configured",
                "step_order": args.data['step_order'],
                "message": "KAI service configured successfully",
                "modified_at": datetime.now().isoformat()
            }
            response = requests.post(
                "http://localhost:8000/api/v1/provision/orbit/notification",
                headers={
                    "Authorization": args.jwt_token,
                    "Content-Type": "application/json"
                },
                json=process_payload
            )
            response.raise_for_status()
            print("Notification sent to main service")
        else:
            pass
        
    except requests.exceptions.RequestException as e:
        print(f"Error configuring KAI service: {e}")
        raise

def main():
    try:
        # Parse command line arguments
        args = parse_args()
        
        # Build connection URI from args
        connection_uri = build_connection_uri(args)
        
        if args.data["process_type"] == "initial_provisioning_orbit":
            print("Initial provisioning for orbit...")
            # Step 1: Deploy services
            run_docker_compose(args.api_key, args)
        
        # Step 2: Configure KAI service
        configure_kai_service(connection_uri, args)
        
        # Step 3: Publish completion message
        if args.data['process_id']:
            args.data['step_order'] += 1
            process_payload = args.data
            response = requests.post(
                "http://localhost:8000/api/v1/provision/orbit/agent",
                headers={
                    "Authorization": args.jwt_token,
                    "Content-Type": "application/json"
                },
                json=process_payload
            )
            print(f"Process payload: {json.dumps(process_payload, indent=2)}")
            response.raise_for_status()
            print("Publuished to agent creation topic")
        else:
            pass
        
        print("Setup completed successfully!")
        
    except Exception as e:
        print(f"Setup failed: {e}")
        raise

if __name__ == "__main__":
    main()