import { Button, Input, List, Space, Typography, App as AntApp } from "antd";
import { SendOutlined } from "@ant-design/icons";
import { useCallback, useEffect, useRef, useState } from "react";
import { client } from "../api/client";
import type { KnowledgeBase } from "../api/client";

interface Citation {
  n: number;
  document_id: number;
  filename: string;
  page: number;
  content: string;
}

interface ChatMessage {
  role: "user" | "assistant";
  content: string;
  citations?: Citation[];
}

interface Props {
  kb: KnowledgeBase;
}

/** 解析 SSE 文本流为事件列表（可能包含半包，返回剩余部分）。 */
function parseSse(buffer: string): { events: any[]; rest: string } {
  const events: any[] = [];
  const parts = buffer.split("\n\n");
  const rest = parts.pop() ?? "";
  for (const raw of parts) {
    const line = raw.trim();
    if (line.startsWith("data: ")) {
      try {
        events.push(JSON.parse(line.slice(6)));
      } catch {
        /* 忽略不完整帧 */
      }
    }
  }
  return { events, rest };
}

export default function ChatPage({ kb }: Props) {
  const { message } = AntApp.useApp();
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState("");
  const [streaming, setStreaming] = useState(false);
  const [openCite, setOpenCite] = useState<Record<number, boolean>>({});
  const conversationId = useRef<number | null>(null);
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    setMessages([]);
    conversationId.current = null;
    setOpenCite({});
  }, [kb.id]);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, streaming]);

  const send = useCallback(async () => {
    const question = input.trim();
    if (!question || streaming) return;
    setInput("");
    setMessages((m) => [...m, { role: "user", content: question }, { role: "assistant", content: "" }]);
    setStreaming(true);

    try {
      // axios 不支持流式读取，SSE 用 fetch 实现
      const resp = await fetch(`/api/kbs/${kb.id}/chat`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${localStorage.getItem("token")}`,
        },
        body: JSON.stringify({ question, conversation_id: conversationId.current }),
      });
      if (!resp.ok || !resp.body) throw new Error(`HTTP ${resp.status}`);

      const reader = resp.body.getReader();
      const decoder = new TextDecoder();
      let buffer = "";
      let answer = "";
      let citations: Citation[] = [];
      for (;;) {
        const { done, value } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        const { events, rest } = parseSse(buffer);
        buffer = rest;
        for (const ev of events) {
          if (ev.type === "meta") {
            conversationId.current = ev.conversation_id;
          } else if (ev.type === "token") {
            answer += ev.content;
            setMessages((m) => {
              const copy = [...m];
              copy[copy.length - 1] = { role: "assistant", content: answer, citations };
              return copy;
            });
          } else if (ev.type === "citations") {
            citations = ev.citations;
            setMessages((m) => {
              const copy = [...m];
              copy[copy.length - 1] = { role: "assistant", content: answer, citations };
              return copy;
            });
          } else if (ev.type === "error") {
            throw new Error(ev.message);
          }
        }
      }
    } catch (e: any) {
      message.error(e.message ?? "请求失败");
      setMessages((m) => {
        const copy = [...m];
        if (copy[copy.length - 1]?.role === "assistant" && !copy[copy.length - 1].content) {
          copy[copy.length - 1] = { role: "assistant", content: "（请求失败，请重试）" };
        }
        return copy;
      });
    } finally {
      setStreaming(false);
    }
  }, [input, streaming, kb.id, message]);

  return (
    <div style={{ display: "flex", flexDirection: "column", height: "calc(100vh - 170px)" }}>
      <div style={{ flex: 1, overflowY: "auto", paddingRight: 8 }}>
        {messages.length === 0 && (
          <Typography.Text type="secondary">
            围绕「{kb.name}」中的文档提问，回答会附带引用来源。
          </Typography.Text>
        )}
        {messages.map((m, i) => (
          <div key={i} style={{ margin: "12px 0", display: "flex", justifyContent: m.role === "user" ? "flex-end" : "flex-start" }}>
            <div style={{ maxWidth: "85%" }}>
              <div
                style={{
                  display: "inline-block",
                  padding: "8px 12px",
                  borderRadius: 10,
                  whiteSpace: "pre-wrap",
                  wordBreak: "break-word",
                  background: m.role === "user" ? "#e6f4ff" : "#fff",
                  border: "1px solid #f0f0f0",
                  textAlign: "left",
                }}
              >
                {m.content || (streaming && i === messages.length - 1 ? "思考中…" : "")}
              </div>
              {m.role === "assistant" && m.citations && m.citations.length > 0 && (
                <div style={{ marginTop: 4 }}>
                  <Button type="link" size="small" style={{ padding: 0 }} onClick={() => setOpenCite((s) => ({ ...s, [i]: !s[i] }))}>
                    引用来源（{m.citations.length}）
                  </Button>
                  {openCite[i] && (
                    <List
                      size="small"
                      bordered
                      style={{ background: "#fff", borderRadius: 8, maxHeight: 260, overflow: "auto", marginTop: 4 }}
                      dataSource={m.citations}
                      renderItem={(c) => (
                        <List.Item>
                          <Typography.Text style={{ fontSize: 12 }}>
                            <Typography.Text strong>[{c.n}] {c.filename}</Typography.Text>
                            {c.page ? ` 第${c.page}页` : ""}
                            <br />
                            <Typography.Text type="secondary">{c.content.slice(0, 200)}{c.content.length > 200 ? "……" : ""}</Typography.Text>
                          </Typography.Text>
                        </List.Item>
                      )}
                    />
                  )}
                </div>
              )}
            </div>
          </div>
        ))}
        <div ref={bottomRef} />
      </div>

      <Space.Compact style={{ width: "100%", marginTop: 12 }}>
        <Input
          placeholder="输入问题，Enter 发送"
          value={input}
          disabled={streaming}
          onChange={(e) => setInput(e.target.value)}
          onPressEnter={send}
          size="large"
        />
        <Button type="primary" size="large" icon={<SendOutlined />} loading={streaming} onClick={send}>
          发送
        </Button>
      </Space.Compact>
    </div>
  );
}
