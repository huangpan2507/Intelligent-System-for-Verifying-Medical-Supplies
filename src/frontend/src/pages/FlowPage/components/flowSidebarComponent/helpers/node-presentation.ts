import { businessText } from "@/pages/BusinessPage/business-i18n";
import {
  businessNodeDescription,
  businessNodeName,
} from "@/pages/BusinessPage/business-node-presentation";

// Presentation only: keep catalog objects, drag payloads and saved configuration unchanged.
const defaults: Record<string, { name: string; description: string | null }> = {
  ChatInput: {
    name: "Chat Input",
    description: "Get chat inputs from the Playground.",
  },
  ChatOutput: {
    name: "Chat Output",
    description: "Display a chat message in the Playground.",
  },
  TextInput: {
    name: "Text Input",
    description: "Get user text inputs.",
  },
  TextOutput: {
    name: "Text Output",
    description: "Sends text output via API.",
  },
  Webhook: {
    name: "Webhook",
    description: null,
  },
  APIRequest: {
    name: "API Request",
    description: "Make HTTP requests using URL or cURL commands.",
  },
  CSVtoData: {
    name: "Load CSV",
    description:
      "Load a CSV file, CSV from a file path, or a valid CSV string and convert it to a list of Data",
  },
  JSONtoData: {
    name: "Load JSON",
    description:
      "Convert a JSON file, JSON from a file path, or a JSON string to a Data object or a list of Data objects",
  },
  MockDataGenerator: {
    name: "Mock Data",
    description: "Generate mock data for testing and development.",
  },
  NewsSearch: {
    name: "News Search",
    description: "Searches Google News via RSS. Returns clean article data.",
  },
  RSSReaderSimple: {
    name: "RSS Reader",
    description: "Fetches and parses an RSS feed.",
  },
  SQLComponent: {
    name: "SQL Database",
    description: "Executes SQL queries on SQLAlchemy-compatible databases.",
  },
  URLComponent: {
    name: "URL",
    description:
      "Fetch content from one or more web pages, following links recursively.",
  },
  UnifiedWebSearch: {
    name: "Web Search",
    description: "Search the web, news, or RSS feeds.",
  },
  A2AAgent: {
    name: "A2A Agent",
    description:
      "Call an A2A (Agent-to-Agent) agent and return its reply. Pick an agent flow in this project, or point at a remote agent by its URL.",
  },
  Agent: {
    name: "Agent",
    description:
      "Define the agent's instructions, then enter a task to complete using tools.",
  },
  EmbeddingModel: {
    name: "Embedding Model",
    description: "Generate embeddings using a specified provider.",
  },
  LanguageModelComponent: {
    name: "Language Model",
    description: "Runs a language model given a specified provider.",
  },
  MCPTools: {
    name: "MCP Tools",
    description: "Connect to an MCP server to use its tools.",
  },
  Memory: {
    name: "Message History",
    description:
      "Stores or retrieves stored chat messages from Langflow tables or an external memory.",
  },
  "Prompt Template": {
    name: "Prompt Template",
    description: "Create a prompt template with dynamic variables.",
  },
  BatchRunComponent: {
    name: "Batch Run",
    description:
      "Runs an LLM on each row of a DataFrame column. If no column is specified, all columns are used.",
  },
  GuardrailValidator: {
    name: "Guardrails",
    description:
      "Validates input text against multiple security and safety guardrails using LLM-based detection.",
  },
  LLMSelectorComponent: {
    name: "LLM Selector",
    description:
      "Routes the input to the most appropriate LLM based on OpenRouter model specifications",
  },
  "Smart Transform": {
    name: "Smart Transform",
    description:
      "Uses an LLM to generate a function for filtering or transforming structured data and messages.",
  },
  SmartRouter: {
    name: "Smart Router",
    description: "Routes an input message using LLM-based categorization.",
  },
  StructuredOutput: {
    name: "Structured Output",
    description:
      "Uses an LLM to generate structured data. Ideal for extraction and consistency.",
  },
  Directory: {
    name: "Directory",
    description: "Recursively load files from a directory.",
  },
  File: {
    name: "Read File",
    description: "Loads and returns the content from uploaded files.",
  },
  FileSystemTool: {
    name: "File System",
    description: "Sandboxed filesystem access for agents.",
  },
  Knowledge: {
    name: "Knowledge",
    description: "Ingest into or retrieve from a Langflow knowledge base.",
  },
  KnowledgeBase: {
    name: "Knowledge Base",
    description: "Search and retrieve data from knowledge.",
  },
  KnowledgeIngestion: {
    name: "Knowledge Ingestion",
    description: "Create or update knowledge in Langflow.",
  },
  MemoryBase: {
    name: "Memory Base",
    description:
      "Retrieve long-term memory from a Memory Base attached to this workflow. When 'Filter by Session' is off, queries run across all sessions.",
  },
  SaveToFile: {
    name: "Write File",
    description:
      "Save content to a file in the specified format and return its path.",
  },
  AlterMetadata: {
    name: "Alter Metadata",
    description: "Adds/Removes Metadata Dictionary on inputs",
  },
  CombineText: {
    name: "Combine Text",
    description:
      "Concatenate two text sources into a single text chunk using a specified delimiter.",
  },
  CreateData: {
    name: "Create Data",
    description: "Dynamically create a Data with a specified number of fields.",
  },
  CreateList: {
    name: "Create List",
    description: "Creates a list of texts.",
  },
  DataFrameOperations: {
    name: "Table Operations",
    description: "Perform various operations on a Table.",
  },
  DataOperations: {
    name: "JSON Operations",
    description: "Perform various operations on a JSON object.",
  },
  DataToDataFrame: {
    name: "Data → DataFrame",
    description:
      "Converts one or multiple Data objects into a DataFrame. Each Data object corresponds to one row. Fields from `.data` become columns, and the `.text` (if present) is placed in a 'text' column.",
  },
  DynamicCreateData: {
    name: "Dynamic Create Data",
    description: "Dynamically create a Data with a specified number of fields.",
  },
  ExtractaKey: {
    name: "Extract Key",
    description:
      "Extract a specific key from a Data object or a list of Data objects and return the extracted value(s) as Data object(s).",
  },
  FilterData: {
    name: "Filter Data",
    description: "Filters a Data object based on a list of keys.",
  },
  FilterDataValues: {
    name: "Filter Values",
    description:
      "Filter a list of data items based on a specified key, filter value, and comparison operator. Check advanced options to select match comparison.",
  },
  JSONCleaner: {
    name: "JSON Cleaner",
    description:
      "Cleans the messy and sometimes incorrect JSON strings produced by LLMs so that they are fully compliant with the JSON spec.",
  },
  MergeDataComponent: {
    name: "Combine Data",
    description: "Combines data using different operations",
  },
  MessagetoData: {
    name: "Message to Data",
    description: "Convert a Message object to a Data object",
  },
  Operations: {
    name: "Data Operations",
    description:
      "Perform operations on Text, JSON, and Tables from a single component.",
  },
  OutputParser: {
    name: "Output Parser",
    description: "Transforms the output of an LLM into a specified format.",
  },
  ParseData: {
    name: "Data to Message",
    description:
      "Convert Data objects into Messages using any {field_name} from input data.",
  },
  ParseDataFrame: {
    name: "Parse DataFrame",
    description:
      "Convert a DataFrame into plain text following a specified template. Each column in the DataFrame is treated as a possible template key, e.g. {col_name}.",
  },
  ParseJSONData: {
    name: "Parse JSON",
    description: "Convert and extract JSON fields.",
  },
  ParserComponent: {
    name: "Parser",
    description: "Extracts text using a template.",
  },
  RegexExtractorComponent: {
    name: "Regex Extractor",
    description: "Extract patterns from text using regular expressions.",
  },
  SelectData: {
    name: "Select Data",
    description: "Select a single data from a list of data.",
  },
  SplitText: {
    name: "Split Text",
    description: "Split text into chunks based on specified criteria.",
  },
  StoreMessage: {
    name: "Message Store",
    description:
      "Stores a chat message or text into Langflow tables or an external memory.",
  },
  TextOperations: {
    name: "Text Operations",
    description:
      "Perform various text processing operations including text-to-DataFrame conversion.",
  },
  TypeConverterComponent: {
    name: "Type Convert",
    description: "Convert between different types (Message, JSON, Table)",
  },
  UpdateData: {
    name: "Update Data",
    description: "Dynamically update or append data with the specified fields.",
  },
  ConditionalRouter: {
    name: "If-Else",
    description:
      "Routes an input message to a corresponding output based on text comparison.",
  },
  DataConditionalRouter: {
    name: "Condition",
    description:
      "Route Data object(s) based on a condition applied to a specified key, including boolean validation.",
  },
  FlowTool: {
    name: "Flow as Tool",
    description: "Construct a Tool from a function that runs the loaded Flow.",
  },
  HumanInput: {
    name: "Human Input",
    description:
      "Pause the flow for a human-in-the-loop (HITL) decision and route on the chosen action.",
  },
  Listen: {
    name: "Listen",
    description: "A component to listen for a notification.",
  },
  LoopComponent: {
    name: "Loop",
    description:
      "Iterates through Data or Message objects, processing items individually and aggregating results from loop inputs.",
  },
  Notify: {
    name: "Notify",
    description:
      "A component to generate a notification to Get Notified component.",
  },
  Pass: {
    name: "Pass",
    description: "Forwards the input message, unchanged.",
  },
  RunFlow: {
    name: "Run Flow",
    description:
      "Executes another flow from within the same project. Can also be used as a tool for agents. \n **Select a Flow to use the tool mode**",
  },
  SubFlow: {
    name: "Sub Flow",
    description:
      "Generates a Component from a Flow, with all of its inputs, and ",
  },
  "ext:verification:VerificationTaskInput@extra": {
    name: "Chat Input 任务输入",
    description: null,
  },
};
export function sidebarNodeName(
  type: string,
  name?: string,
): string | undefined {
  if (defaults[type]?.name === name && name)
    return businessText(`sidebar.node.${type.replaceAll(":", "_")}.name`);
  return businessNodeName(type, name);
}
export function sidebarNodeDescription(
  type: string,
  description?: string,
): string | undefined {
  if (description && defaults[type]?.description === description)
    return businessText(
      `sidebar.node.${type.replaceAll(":", "_")}.description`,
    );
  return businessNodeDescription(type, description);
}
