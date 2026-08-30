import { Button, Empty, List, Popconfirm, Tag, Typography, Upload } from "antd";
import { DeleteOutlined } from "@ant-design/icons";
import { useCallback, useEffect, useRef, useState } from "react";
import { client } from "../api/client";
import type { KnowledgeBase } from "../api/client";

export interface DocumentInfo {
  id: number;
  filename: string;
  file_type: string;
  size: number;
  status: "pending" | "parsing" | "ready" | "failed";
  chunk_count: number;
  error: string;
  created_at: number;
}

const STATUS: Record<DocumentInfo["status"], { color: string; label: string }> = {
  pending: { color: "default", label: "排队中" },
  parsing: { color: "processing", label: "解析中" },
  ready: { color: "success", label: "已就绪" },
  failed: { color: "error", label: "失败" },
};

interface Props {
  kb: KnowledgeBase;
  onChanged?: () => void;
}

export default function DocumentsPage({ kb, onChanged }: Props) {
  const [docs, setDocs] = useState<DocumentInfo[]>([]);
  const [loading, setLoading] = useState(true);
  const [uploading, setUploading] = useState(false);
  const timer = useRef<ReturnType<typeof setInterval> | null>(null);

  const load = useCallback(async () => {
    try {
      setDocs((await client.get<DocumentInfo[]>(`/kbs/${kb.id}/documents`)).data);
    } finally {
      setLoading(false);
    }
  }, [kb.id]);

  const busy = docs.some((d) => d.status === "pending" || d.status === "parsing");

  useEffect(() => {
    load();
  }, [load]);

  // 有文档在解析时每 3 秒轮询一次，全部完成后停止
  useEffect(() => {
    if (busy && !timer.current) {
      timer.current = setInterval(load, 3000);
    } else if (!busy && timer.current) {
      clearInterval(timer.current);
      timer.current = null;
    }
    return () => {
      if (timer.current) {
        clearInterval(timer.current);
        timer.current = null;
      }
    };
  }, [busy, load]);

  async function customRequest(options: any) {
    const form = new FormData();
    form.append("file", options.file);
    setUploading(true);
    try {
      await client.post(`/kbs/${kb.id}/documents`, form);
      options.onSuccess?.(null);
      load();
      onChanged?.();
    } catch (e: any) {
      options.onError?.(e);
      alert(e.response?.data?.detail ?? "上传失败");
    } finally {
      setUploading(false);
    }
  }

  async function removeDoc(id: number) {
    await client.delete(`/documents/${id}`);
    load();
  }

  return (
    <div>
      <Upload.Dragger
        multiple
        accept=".pdf,.docx,.md,.txt,.xlsx"
        customRequest={customRequest}
        showUploadList={false}
        disabled={uploading}
        style={{ background: "#fafafa", marginBottom: 16 }}
      >
        <Typography.Text>
          {uploading ? "上传中……" : "点击或拖拽文件上传（PDF / Word / Excel / Markdown / TXT，≤50MB），上传后自动解析入库"}
        </Typography.Text>
      </Upload.Dragger>

      <List
        loading={loading}
        dataSource={docs}
        locale={{ emptyText: <Empty description="还没有文档" /> }}
        renderItem={(d) => (
          <List.Item
            actions={[
              <Popconfirm key="del" title="删除该文档及其向量数据？" onConfirm={() => removeDoc(d.id)}>
                <Button type="text" danger icon={<DeleteOutlined />} />
              </Popconfirm>,
            ]}
          >
            <List.Item.Meta
              title={
                <span>
                  {d.filename}{" "}
                  <Tag color={STATUS[d.status].color}>{STATUS[d.status].label}</Tag>
                  {d.status === "ready" && (
                    <Typography.Text type="secondary" style={{ fontSize: 12 }}>
                      {d.chunk_count} 个片段
                    </Typography.Text>
                  )}
                </span>
              }
              description={d.status === "failed" ? `失败原因：${d.error}` : `${(d.size / 1024).toFixed(1)} KB · ${new Date(d.created_at * 1000).toLocaleString()}`}
            />
          </List.Item>
        )}
      />
    </div>
  );
}
