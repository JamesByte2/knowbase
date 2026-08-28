import { Button, Layout, Menu, Typography, theme } from "antd";
import { BookOutlined, CommentOutlined } from "@ant-design/icons";
import { useState } from "react";

const { Header, Sider, Content } = Layout;

// 骨架占位：M4 阶段替换为 登录 / 知识库管理 / 文档上传 / 对话 四个页面
export default function App() {
  const { token } = theme.useToken();
  const [page, setPage] = useState("kbs");

  return (
    <Layout style={{ minHeight: "100vh" }}>
      <Sider theme="light" style={{ borderRight: `1px solid ${token.colorBorderSecondary}` }}>
        <div style={{ padding: 16 }}>
          <Typography.Title level={4} style={{ margin: 0 }}>
            KnowBase
          </Typography.Title>
        </div>
        <Menu
          mode="inline"
          selectedKeys={[page]}
          onClick={(e) => setPage(e.key)}
          items={[
            { key: "kbs", icon: <BookOutlined />, label: "知识库" },
            { key: "chat", icon: <CommentOutlined />, label: "对话" },
          ]}
        />
      </Sider>
      <Layout>
        <Header
          style={{ background: token.colorBgContainer, borderBottom: `1px solid ${token.colorBorderSecondary}` }}
        />
        <Content style={{ padding: 24, background: token.colorBgLayout }}>
          <Typography.Text type="secondary">
            页面骨架占位 —— M1 只跑通前后端联通，M4 完成完整界面。
          </Typography.Text>
          <div style={{ marginTop: 16 }}>
            <Button type="primary" onClick={() => setPage("kbs")}>
              开始使用
            </Button>
          </div>
        </Content>
      </Layout>
    </Layout>
  );
}
