from typing import List, Optional
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_openai import ChatOpenAI
from gen_ui_backend.tools.github import github_repo, GithubRepoInput
from gen_ui_backend.tools.invoice import invoice_parser, Invoice
from gen_ui_backend.tools.weather import weather_data, WeatherInput
from typing_extensions import TypedDict
from langchain.output_parsers.openai_tools import JsonOutputToolsParser
from langgraph.graph import StateGraph, END
from langchain_core.messages import AIMessage, HumanMessage
from langchain.pydantic_v1 import BaseModel

class GenerativeUIState(TypedDict, total=False):
    input: HumanMessage
    result: Optional[str]
    """Plain text response if no tool was used."""
    tool_calls: Optional[List[dict]]
    """A list of parsed tool calls."""
    tool_result: Optional[dict]
    """The result of a tool call."""

def invoke_model(state: GenerativeUIState) -> GenerativeUIState:
    tools_parser = JsonOutputToolsParser()
    initial_prompt = ChatPromptTemplate.from_messages([
        ("system", "You are a helpful assistant. You're provided a list of tools, and an input from the user.\n" +
            "Your job is to determine whether or not you have a tool which can handle the users input, or respond with plain text."),
        MessagesPlaceholder("input")
    ])
    model = ChatOpenAI(model="gpt-4o", temperature=0, streaming=True)
    tools = [github_repo, invoice_parser, weather_data]
    model_with_tools = model.bind_tools(tools)
    chain = initial_prompt | model_with_tools
    # maybe stream this result?
    result: AIMessage = chain.invoke(input=state["input"])

    if isinstance(result.tool_calls, list) and len(result.tool_calls) > 0:
        print("Tool calls selected!")
        parsed_tools = tools_parser.invoke(result)
        print(parsed_tools)
        return {
            "tool_calls": parsed_tools
        }
    else:
        return {
            "result": result.content
        }
    
def invoke_tools_or_return(state: GenerativeUIState) -> str:
    if "result" in state and isinstance(state["result"], str):
        print("---RETURNING PLAIN TEXT---")
        return END
    elif "tool_calls" in state and isinstance(state["tool_calls"], list):
        print("---RETURNING TOOL CALLS---")
        return "invoke_tools"
    else:
        raise ValueError("Invalid state. No result or tool calls found.")

def invoke_tools(state: GenerativeUIState) -> GenerativeUIState:
    tools_map = {
        "github-repo": github_repo,
        "invoice-parser": invoice_parser,
        "weather-data": weather_data
    }
    tool = state["tool_calls"][0]
    selected_tool = tools_map[tool["type"]]

    return {
        "tool_result": selected_tool.invoke(tool["args"])
    }

def create_graph():
    workflow = StateGraph(GenerativeUIState)

    workflow.add_node("invoke_model", invoke_model)
    workflow.add_node("invoke_tools", invoke_tools)
    workflow.add_conditional_edges("invoke_model", invoke_tools_or_return)
    workflow.set_entry_point("invoke_model")
    workflow.set_finish_point("invoke_tools")

    graph = workflow.compile()
    return graph
