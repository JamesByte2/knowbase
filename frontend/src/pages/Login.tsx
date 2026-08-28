import { Button, Card, Form, Input, Tabs, Typography, App as AntApp } from "antd";
import { useState } from "react";
import { client } from "../api/client";

interface Props {
  onLogin: (token: string) => void;
}

export default function LoginPage({ onLogin }: Props) {
  const { message } = AntApp.useApp();
  const [mode, setMode] = useState<"login" | "register">("login");
  const [loading, setLoading] = useState(false);
  const [form] = Form.useForm<{ email: string; password: string }>();

  async function submit(values: { email: string; password: string }) {
    setLoading(true);
    try {
      const r = await client.post(`/auth/${mode}`, values);
      localStorage.setItem("token", r.data.token);
      onLogin(r.data.token);
    } catch (e: any) {
      message.error(e.response?.data?.detail ?? "请求失败");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div style={{ minHeight: "100vh", display: "grid", placeItems: "center", background: "#f5f5f5" }}>
      <Card style={{ width: 380 }}>
        <Typography.Title level={3} style={{ textAlign: "center", marginBottom: 24 }}>
          KnowBase · AI 知识库问答
        </Typography.Title>
        <Tabs
          activeKey={mode}
          onChange={(k) => setMode(k as "login" | "register")}
          items={[
            { key: "login", label: "登录" },
            { key: "register", label: "注册" },
          ]}
        />
        <Form form={form} layout="vertical" onFinish={submit} requiredMark={false}>
          <Form.Item name="email" label="邮箱" rules={[{ required: true, message: "请输入邮箱" }]}>
            <Input placeholder="you@example.com" autoComplete="email" />
          </Form.Item>
          <Form.Item
            name="password"
            label="密码"
            rules={[
              { required: true, message: "请输入密码" },
              {
                validator: (_, value) =>
                  mode === "register" && String(value ?? "").length < 8
                    ? Promise.reject(new Error("密码至少 8 位"))
                    : Promise.resolve(),
              },
            ]}
          >
            <Input.Password placeholder="至少 8 位" autoComplete="current-password" />
          </Form.Item>
          <Button type="primary" htmlType="submit" block loading={loading}>
            {mode === "login" ? "登录" : "注册并登录"}
          </Button>
        </Form>
      </Card>
    </div>
  );
}
