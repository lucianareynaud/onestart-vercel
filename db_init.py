#!/usr/bin/env python3
import os
import sys
import time
import logging
from db import supabase

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def create_table_if_not_exists(table_name, fields):
    """Create a table in Supabase if it doesn't exist yet"""
    try:
        client = supabase.admin_client if supabase.admin_client else supabase.client
        if not client:
            logger.warning("No Supabase client available. Skipping table creation.")
            return
            
        # Check if table exists by querying it
        try:
            # Use a simpler query that doesn't use count() function
            client.table(table_name).select("*").limit(1).execute()
            logger.info(f"Table {table_name} already exists. Skipping.")
            return
        except Exception as e:
            if "relation" in str(e) and "does not exist" in str(e):
                logger.info(f"Table {table_name} does not exist. Creating...")
            else:
                logger.error(f"Error checking table {table_name}: {str(e)}")
                return
        
        # Create SQL query to create the table
        query = f"CREATE TABLE IF NOT EXISTS {table_name} ("
        for i, (name, type_def) in enumerate(fields):
            query += f"{name} {type_def}"
            if i < len(fields) - 1:
                query += ","
        query += ");"
        
        # Execute the query using rpc
        result = client.rpc("exec_sql", {"query": query}).execute()
        logger.info(f"Table {table_name} created successfully")
        return True
    except Exception as e:
        logger.error(f"Error creating table {table_name}: {str(e)}")
        return False

def init_database():
    """Initialize the database tables"""
    # Define the tables to create
    tables = {
        "analyses": [
            ("id", "uuid PRIMARY KEY DEFAULT uuid_generate_v4()"),
            ("transcript_id", "uuid REFERENCES transcripts(id) ON DELETE CASCADE"),
            ("sales_data", "jsonb"),
            ("call_analysis", "jsonb"),
            ("created_at", "timestamptz DEFAULT now()"),
            ("updated_at", "timestamptz DEFAULT now()")
        ],
        "website_enrichments": [
            ("id", "uuid PRIMARY KEY DEFAULT uuid_generate_v4()"),
            ("transcript_id", "uuid REFERENCES transcripts(id) ON DELETE CASCADE"),
            ("website_url", "text NOT NULL"),
            ("status", "text DEFAULT 'pending'"),
            ("scraped_at", "timestamptz"),
            ("parsed_data", "jsonb"),
            ("created_at", "timestamptz DEFAULT now()"),
            ("updated_at", "timestamptz DEFAULT now()")
        ],
        "linkedin_enrichments": [
            ("id", "uuid PRIMARY KEY DEFAULT uuid_generate_v4()"),
            ("transcript_id", "uuid REFERENCES transcripts(id) ON DELETE CASCADE"),
            ("linkedin_url", "text NOT NULL"),
            ("status", "text DEFAULT 'pending'"),
            ("scraped_at", "timestamptz"),
            ("profile_data", "jsonb"),
            ("created_at", "timestamptz DEFAULT now()"),
            ("updated_at", "timestamptz DEFAULT now()")
        ]
    }

    # Wait for Supabase to be ready
    if not supabase.is_demo_mode:
        retries = 5
        while retries > 0:
            try:
                if supabase.client:
                    # Check if we can connect
                    # Use a simpler query to test connection
                    supabase.client.table("transcripts").select("*").limit(1).execute()
                    logger.info("Connected to Supabase successfully")
                    break
                else:
                    logger.warning("No Supabase client available. Skipping table initialization.")
                    return
            except Exception as e:
                logger.warning(f"Error connecting to Supabase: {str(e)}. Retrying...")
                retries -= 1
                time.sleep(5)
        
        if retries == 0:
            logger.error("Failed to connect to Supabase after multiple attempts. Skipping table initialization.")
            return
        
        # Create the tables
        for table_name, fields in tables.items():
            create_table_if_not_exists(table_name, fields)
    else:
        logger.info("Running in demo mode. Skipping table initialization.")

if __name__ == "__main__":
    init_database() 