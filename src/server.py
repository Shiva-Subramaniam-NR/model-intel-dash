from mcp.server.fastmcp import FastMCP
from providers.azure import fetch_model_pricing, fetch_model_retirements
from providers.azure import fetch_whats_new, fetch_model_availability, fetch_model_info

#this is mcp server name 
mcp = FastMCP("model-intel")

#Decorator registers this function as an MCP tool. Any MCP client can now discover and call it. 
#The docstring becomes the tool's description — clients use it to understand what the tool does

@mcp.tool()
def hello_checker() -> str:
    """Simple hello check tool to see if the server is running or not."""
    return "Welcome to the MCP server."

@mcp.tool()
async def get_model_summary(provider: str) -> str:
    """this brings model information from the provider given as input by user."""
    if provider.lower() == "azure":
        result = await fetch_model_retirements()
        return result
    else:
        return f"Provider '{provider}' is not supported. Please use 'azure'."

@mcp.tool()
def get_model_pricing(region: str) -> str:
    """this brings model pricing information from the provider given as input by user."""
    result = fetch_model_pricing(region)
    return result
    
@mcp.tool()
async def get_model_availability():
    """this brings model availability information from the provider given as input by user."""
    result = await fetch_model_availability()
    return result
        
@mcp.tool()
async def get_model_info():
    """this brings information for the model given as input by user."""
    result = await fetch_model_info()
    return result
        

@mcp.tool()
async def get_whats_new() -> str:
    """this brings what's new information from the provider given as input by user."""
    result = await fetch_whats_new()
    return result

if __name__ == "__main__": 
    # Start the MCP server. It will listen for incoming requests and handle them using the registered tools.
    mcp.run()
