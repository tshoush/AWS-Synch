from app import create_app
import os
import socket
import asyncio
from hypercorn.config import Config
from hypercorn.asyncio import serve

app = create_app()

def find_available_port(start_port=5000, max_attempts=100):
    """Find an available port starting from start_port"""
    for port in range(start_port, start_port + max_attempts):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            try:
                sock.bind(('', port))
                return port
            except OSError:
                continue
    raise RuntimeError(f"Could not find available port in range {start_port}-{start_port + max_attempts}")

async def main():
    """Main async entry point"""
    port = find_available_port()
    
    # Configure Hypercorn
    config = Config()
    config.bind = [f"0.0.0.0:{port}"]
    config.use_reloader = True
    config.accesslog = "-"  # Log to stdout
    
    print(f"\n{'='*50}")
    print(f"Starting DDI Sync Manager (Async) on port {port}")
    print(f"Access the application at: http://localhost:{port}")
    print(f"{'='*50}\n")
    
    # Run the async server
    await serve(app, config)

if __name__ == '__main__':
    # For development
    if os.environ.get('ENV') == 'development':
        port = find_available_port()
        print(f"\n{'='*50}")
        print(f"Starting DDI Sync Manager (Development) on port {port}")
        print(f"Access the application at: http://localhost:{port}")
        print(f"{'='*50}\n")
        app.run(host='0.0.0.0', port=port, debug=True)
    else:
        # Production mode with Hypercorn
        asyncio.run(main())