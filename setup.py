import os
import json
import time
import subprocess
import requests
import argparse
import urllib.parse
from dotenv import load_dotenv
from google.cloud import pubsub_v1

def parse_args():
    """Parse command line arguments"""
    parser = argparse.ArgumentParser(description='Setup Orbit services and configuration')
    parser.add_argument('--api-key', required=True, help='API Key for authentication')
    
    # Database connection group - either URI or individual parameters
    db_group = parser.add_mutually_exclusive_group(required=True)
    db_group.add_argument('--db-connection-uri', help='Database connection URI')
    db_group.add_argument('--db-host', help='Database host')
    parser.add_argument('--db-port', type=int, default=5432, help='Database port (default: 5432)')
    parser.add_argument('--db-name', help='Database name')
    parser.add_argument('--db-user', help='Database username')
    parser.add_argument('--db-password', help='Database password')
    
    # Geolocation arguments
    parser.add_argument('--fact-table', help='Fact table name for geolocation')
    parser.add_argument('--province-col', help='Province column name in fact table')
    parser.add_argument('--city-col', help='City column name in fact table')
    parser.add_argument('--district-col', help='District column name in fact table')
    parser.add_argument('--subdistrict-col', help='Sub-district column name in fact table')
    # Static location values
    parser.add_argument('--province', help='Static province value')
    parser.add_argument('--city', help='Static city value')
    parser.add_argument('--district', help='Static district value')
    parser.add_argument('--subdistrict', help='Static sub-district value')
    return parser.parse_args()

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

def run_docker_compose(api_key):
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
    except subprocess.CalledProcessError as e:
        print(f"Error starting docker services: {e}")
        raise
    except IOError as e:
        print(f"Error updating .env.orbit file: {e}")
        raise

def should_run_geolocation(args):
    """Check if geolocation migration should be run based on provided arguments"""
    return args.db_connection_uri and args.fact_table

def setup_geolocation(args):
    """Execute geolocation migration if required arguments are provided"""
    print("Setting up geolocation feature...")
    try:
        migration_script = os.path.join(
            os.path.dirname(os.path.abspath(__file__)),
            'geo-migration-script',
            'geolocation-migration-script.py'
        )
        
        # Prepare command arguments
        cmd = ['uv', 'run', migration_script]  # Changed from python to uv run
        
        # Add connection parameters (either URI or individual params)
        if args.db_connection_uri:
            cmd.extend(['--connection-uri', args.db_connection_uri])
        else:
            cmd.extend(['--host', args.db_host])
            cmd.extend(['--port', str(args.db_port)])
            cmd.extend(['--database', args.db_name])
            cmd.extend(['--user', args.db_user])
            
        # Add fact table name
        cmd.extend(['--fact-table', args.fact_table])
        
        # Add optional column names if provided
        if args.province_col:
            cmd.extend(['--province-col', args.province_col])
        if args.city_col:
            cmd.extend(['--city-col', args.city_col])
        if args.district_col:
            cmd.extend(['--district-col', args.district_col])
        if args.subdistrict_col:
            cmd.extend(['--subdistrict-col', args.subdistrict_col])
            
        # Add static values if provided
        if args.province:
            cmd.extend(['--province', args.province])
        if args.city:
            cmd.extend(['--city', args.city])
        if args.district:
            cmd.extend(['--district', args.district])
        if args.subdistrict:
            cmd.extend(['--subdistrict', args.subdistrict])
        
        subprocess.run(cmd, check=True)
        print("Geolocation setup completed successfully")
        
    except subprocess.CalledProcessError as e:
        print(f"Error during geolocation setup: {e}")
        raise

def configure_kai_service(connection_uri):
    """Configure KAI service with database connections and schemas"""
    # Load environment variables
    kai_address = "http://localhost:8005"  # Using localhost since script runs outside Docker
    
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
        
    except requests.exceptions.RequestException as e:
        print(f"Error configuring KAI service: {e}")
        raise

def publish_domain_created():
    """Publish message to create.domain topic"""
    publisher = pubsub_v1.PublisherClient()
    topic_path = publisher.topic_path(
        os.getenv('GOOGLE_CLOUD_PROJECT'),
        'create.domain'
    )
    
    message = {
        "status": "completed",
        "timestamp": time.time()
    }
    
    future = publisher.publish(
        topic_path,
        json.dumps(message).encode('utf-8')
    )
    print(f"Message published: {future.result()}")

def main():
    try:
        # Parse command line arguments
        args = parse_args()
        
        # Build connection URI from args
        connection_uri = build_connection_uri(args)
        
        # Step 1: Deploy services
        run_docker_compose(args.api_key)
        
        # Step 2: Setup geolocation if required args are provided
        if args.fact_table:
            setup_geolocation(args)
        
        # Step 3: Configure KAI service
        configure_kai_service(connection_uri)
        
        # Step 4: Publish completion message
        # publish_domain_created()
        
        print("Setup completed successfully!")
        
    except Exception as e:
        print(f"Setup failed: {e}")
        raise

if __name__ == "__main__":
    main()