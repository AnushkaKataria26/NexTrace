import argparse
import random
import os
from datetime import datetime, timedelta
from faker import Faker

def generate_logs(num_lines, output_file):
    fake = Faker()
    levels = ["INFO", "WARN", "ERROR", "DEBUG"]
    weights = [0.6, 0.2, 0.05, 0.15] # INFO most common, ERROR rarer
    sources = ["api-gateway", "auth-service", "db-service", "payment-service", "notification-service"]
    
    templates = [
        "Connection timeout to {service}",
        "Request processed in {n}ms",
        "Failed to authenticate user {id}",
        "{sentence}"
    ]

    now = datetime.now() - timedelta(days=1)
    
    # Ensure directory exists
    os.makedirs(os.path.dirname(os.path.abspath(output_file)), exist_ok=True)
    
    with open(output_file, 'w') as f:
        for i in range(num_lines):
            # Time progresses slightly
            now += timedelta(milliseconds=random.randint(10, 5000))
            timestamp = now.strftime("%Y-%m-%d %H:%M:%S")
            level = random.choices(levels, weights=weights)[0]
            source = random.choice(sources)
            
            tmpl = random.choice(templates)
            if "{service}" in tmpl:
                msg = tmpl.format(service=random.choice(sources))
            elif "{n}" in tmpl:
                msg = tmpl.format(n=random.randint(5, 2000))
            elif "{id}" in tmpl:
                msg = tmpl.format(id=fake.uuid4()[:8])
            else:
                msg = fake.sentence()
                
            log_line = f"{timestamp} {level} {source} {msg}\n"
            f.write(log_line)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Generate synthetic logs for NexTrace.")
    parser.add_argument("--lines", type=int, default=1000, help="Number of log lines to generate")
    parser.add_argument("--output", type=str, default="data/sample.log", help="Output file path")
    args = parser.parse_args()
    
    generate_logs(args.lines, args.output)
    print(f"Generated {args.lines} log lines in {args.output}")
