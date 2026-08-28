import { Button, Empty, List, Modal, Popconfirm, Typography, App as AntApp, Form, Input } from "antd";
import { DeleteOutlined, PlusOutlined } from "@ant-design/icons";
import { useCallback, useEffect, useState } from "react";
import { client, KnowledgeBase } from "../api/client";

export default function KnowledgeBasesPage() {
  const { message } = AntApp.useApp();
  const [kbs, setKbs] = useState<KnowledgeBase[]>([]);
  const [loading, setLoading] = useState(true);
  const [modalOpen, setModalOpen] = useState(false);
  const [form] = Form.useForm<{ name: string; description?: string }>();

  const load = useCallback(async () => {
    setLoading(true);
    try {
      setKbs((await client.get<KnowledgeBase[]>("/kbs")).data);
    } catch (e: any) {
      message.error(e.response?.data?.detail ?? "加载失败");
    } finally {
      setLoading(false);
    }
  }, [message]);

  useEffect(() => {
    load();
  }, [load]);

  async function create(values: { name: string; description?: string }) {
    try {
      await client.post("/kbs", values);
      message.success("知识库已创建");
      setModalOpen(false);
      form.resetFields();
      load();
    } catch (e: any) {
      message.error(e.response?.data?.detail ?? "创建失败");
    }
  }

  async function remove(id: number) {
    try {
      await client.delete(`/kbs/${id}`);
      message.success("已删除");
      load();
    } catch (e: any) {
      message.error(e.response?.data?.detail ?? "删除失败");
    }
  }

  return (
    <div style={{ maxWidth: 720, margin: "0 auto" }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 16 }}>
        <Typography.Title level={4} style={{ margin: 0 }}>
          我的知识库
        </Typography.Title>
        <Button type="primary" icon={<PlusOutlined />} onClick={() => setModalOpen(true)}>
          新建知识库
        </Button>
      </div>

      <List
        loading={loading}
        dataSource={kbs}
        locale={{ emptyText: <Empty description="还没有知识库，点击右上角新建" /> }}
        renderItem={(kb) => (
          <List.Item
            actions={[
              <Popconfirm key="del" title="确定删除该知识库及其全部文档？" onConfirm={() => remove(kb.id)}>
                <Button type="text" danger icon={<DeleteOutlined />} />
              </Popconfirm>,
            ]}
          >
            <List.Item.Meta title={kb.name} description={kb.description || "无描述"} />
          </List.Item>
        )}
      />

      <Modal
        title="新建知识库"
        open={modalOpen}
        onCancel={() => setModalOpen(false)}
        onOk={() => form.submit()}
        okText="创建"
        cancelText="取消"
      >
        <Form form={form} layout="vertical" onFinish={create}>
          <Form.Item name="name" label="名称" rules={[{ required: true, message: "请输入名称" }]}>
            <Input placeholder="例如：产品手册知识库" maxLength={64} />
          </Form.Item>
          <Form.Item name="description" label="描述">
            <Input.TextArea placeholder="这个知识库用来回答什么问题？" rows={3} maxLength={256} />
          </Form.Item>
        </Form>
      </Modal>
    </div>
  );
}
