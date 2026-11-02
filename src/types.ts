export interface ToolCallItem {
  id: string;
  name: string;
  arguments: Record<string, any>;
  output?: string;
  is_error?: boolean;
}

export interface ChatMessage {
  role: 'user' | 'assistant' | 'tool';
  content?: string;
  thinking?: string;
  tool_calls?: ToolCallItem[];
  tool_results?: Array<{
    tool_call_id: string;
    name: string;
    output: string;
    is_error?: boolean;
  }>;
}

export interface ArtifactItem {
  name: string;
  path: string;
  summary: string;
  user_facing: boolean;
  request_feedback: boolean;
  status: string;
  updated_at: string;
  content: string;
}

export interface CredentialStatus {
  key: string;
  label: string;
  target_name: string;
  username?: string;
  is_configured: boolean;
  source: 'wincred' | 'env' | 'none';
  masked_preview: string;
}

export interface WindowsTargetItem {
  target_name: string;
  username: string;
  comment: string;
}

export interface QuestionItem {
  question: string;
  options: string[];
  is_multi_select?: boolean;
}

export interface HITLApprovalRequest {
  conversation_id: string;
  approval_id: string;
  tool_name: string;
  command_line: string;
  summary: string;
}
