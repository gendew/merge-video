import React, { useEffect, useMemo, useState } from 'react';
import {
  Form,
  Input,
  Radio,
  Switch,
  Select,
  Upload,
  Button,
  Space,
  message,
  Typography,
  Card,
  Divider,
  Tag,
  Alert,
  Spin,
  List,
  InputNumber,
} from 'antd';
import {
  UploadOutlined,
  CloudUploadOutlined,
  PlayCircleOutlined,
  ReloadOutlined,
  DownloadOutlined,
  ArrowUpOutlined,
  ArrowDownOutlined,
  DeleteOutlined,
} from '@ant-design/icons';
import axios from 'axios';

const { Title, Paragraph, Text } = Typography;
const { Dragger } = Upload;

const MERGE_OPTIONS = [
  { label: 'A: 原始分辨率拼接', value: 'A' },
  { label: 'B: 缩放到最大分辨率', value: 'B' },
  { label: 'C: 缩放到第一个视频分辨率', value: 'C' },
];

const VOICE_MIX_OPTIONS = [
  { label: 'A: 覆盖原声轨', value: 'A' },
  { label: 'B: 混合，原声减半', value: 'B' },
  { label: 'C: 原声轨 + 配音背景 (30%)', value: 'C' },
];

const TTS_OPTIONS = [
  { label: 'A: 默认', value: 'A' },
  { label: 'B: 男声', value: 'B' },
  { label: 'C: 女声', value: 'C' },
];

const OUTPUT_FORMATS = [
  { label: 'mp4', value: 'mp4' },
  { label: 'mov', value: 'mov' },
  { label: 'mkv', value: 'mkv' },
];

const API_BASE = '/api';

export default function App() {
  const [form] = Form.useForm();
  const [videos, setVideos] = useState([]);
  const [voiceList, setVoiceList] = useState([]);
  const [tailImage, setTailImage] = useState([]);
  const [submitting, setSubmitting] = useState(false);
  const [jobId, setJobId] = useState('');
  const [status, setStatus] = useState('');
  const [outputPath, setOutputPath] = useState('');
  const [errorMsg, setErrorMsg] = useState('');
  const [downloadUrl, setDownloadUrl] = useState('');
  const [polling, setPolling] = useState(false);

  const stopPolling = () => setPolling(false);

  useEffect(() => () => stopPolling(), []);

  useEffect(() => {
    let timer;
    if (polling && jobId) {
      const poll = async () => {
        try {
          const res = await axios.get(`${API_BASE}/status/${jobId}`);
          const data = res.data;
          setStatus(data.status);
          setOutputPath(data.output_path || '');
          setErrorMsg(data.error || '');
          if (data.status === 'done') {
            setDownloadUrl(`${API_BASE}/result/${jobId}`);
            stopPolling();
          } else if (data.status === 'error') {
            stopPolling();
          }
        } catch (err) {
          console.error(err);
          stopPolling();
          message.error('查询状态失败');
        }
      };
      poll();
      timer = setInterval(poll, 2000);
    }
    return () => {
      if (timer) clearInterval(timer);
    };
  }, [polling, jobId]);

  const handleSubmit = async (values) => {
    if (!videos.length) {
      message.warning('请至少选择一个视频文件');
      return;
    }
    setSubmitting(true);
    setStatus('');
    setErrorMsg('');
    setDownloadUrl('');
    try {
      const fd = new FormData();
      videos.forEach((item) => {
        fd.append('files', item.file);
      });
      fd.append('trims', JSON.stringify(videos.map((v) => Number(v.trim) || 0)));
      fd.append('trim_modes', JSON.stringify(videos.map((v) => v.trimMode || 'start')));
      fd.append('merge_mode', values.merge_mode);
      fd.append('use_voice', values.use_voice);
      fd.append('voice_mix_mode', values.voice_mix_mode);
      fd.append('tts_voice', values.tts_voice);
      fd.append('output_format', values.output_format);
      fd.append('output_name', values.output_name || 'web_output');
      fd.append('tail_duration', Number(values.tail_duration) || 0);
      if (values.voice_text) {
        fd.append('voice_text', values.voice_text);
      }
      if (voiceList.length) {
        fd.append('voice_file', voiceList[0].originFileObj);
      }
      if (tailImage.length) {
        fd.append('tail_image', tailImage[0].originFileObj);
      }

      const res = await axios.post(`${API_BASE}/merge`, fd, {
        headers: { 'Content-Type': 'multipart/form-data' },
      });
      const job = res.data.job_id;
      setJobId(job);
      setStatus(res.data.status || 'pending');
      setPolling(true);
      message.success(`任务已提交：${job}`);
    } catch (err) {
      console.error(err);
      message.error('提交失败，请检查后台日志或网络');
    } finally {
      setSubmitting(false);
    }
  };

  const resetForm = () => {
    form.resetFields();
    setVideos([]);
    setVoiceList([]);
    setTailImage([]);
    setJobId('');
    setStatus('');
    setOutputPath('');
    setErrorMsg('');
    setDownloadUrl('');
    stopPolling();
  };

  const statusTag = useMemo(() => {
    if (!status) return <Tag>未开始</Tag>;
    const map = {
      pending: <Tag color="default">排队中</Tag>,
      running: <Tag color="processing">运行中</Tag>,
      done: <Tag color="success">完成</Tag>,
      error: <Tag color="error">失败</Tag>,
    };
    return map[status] || <Tag>{status}</Tag>;
  }, [status]);

  const handleVideoUpload = ({ fileList }) => {
    setVideos((prev) => {
      const prevMap = Object.fromEntries(
        prev.map((v) => [v.uid, { trim: v.trim || 0, trimMode: v.trimMode || 'start' }]),
      );
      return fileList.map((f) => {
        const prevItem = prevMap[f.uid] || {};
        return {
          uid: f.uid,
          name: f.name,
          file: f.originFileObj || f,
          trim: prevItem.trim ?? 0,
          trimMode: prevItem.trimMode || 'start',
        };
      });
    });
  };

  const moveVideo = (index, direction) => {
    setVideos((prev) => {
      const next = [...prev];
      const target = index + direction;
      if (target < 0 || target >= prev.length) return prev;
      [next[index], next[target]] = [next[target], next[index]];
      return next;
    });
  };

  const updateTrim = (uid, value) => {
    setVideos((prev) =>
      prev.map((v) => (v.uid === uid ? { ...v, trim: Math.max(0, value || 0) } : v)),
    );
  };

  const updateTrimMode = (uid, mode) => {
    setVideos((prev) => prev.map((v) => (v.uid === uid ? { ...v, trimMode: mode } : v)));
  };

  const removeVideo = (uid) => {
    setVideos((prev) => prev.filter((v) => v.uid !== uid));
  };

  return (
    <div className="page">
      <div className="hero">
        <Title level={2} style={{ color: '#fff', marginBottom: 4 }}>
          Video Merge Voiceover · Web
        </Title>
        <Paragraph style={{ color: '#f0f5ff', marginBottom: 0 }}>
          多视频拼接 + 配音 + TTS，Ant Design 前端，FastAPI 后端，局域网可用。
        </Paragraph>
      </div>

      <Card className="card" title="合成配置" bordered={false}>
        <Form
          layout="vertical"
          form={form}
          initialValues={{
            merge_mode: 'A',
            use_voice: false,
            voice_mix_mode: 'B',
            tts_voice: 'A',
            output_format: 'mp4',
            output_name: 'web_output',
            tail_duration: 0,
          }}
          onFinish={handleSubmit}
        >
          <Form.Item
            label="输入视频（可多选，支持拖拽排序）"
            required
            tooltip="按列表顺序拼接，可设置每段截取前/后 N 秒"
          >
            <Dragger
              multiple
              accept="video/*"
              beforeUpload={() => false}
              fileList={videos.map((v) => ({
                uid: v.uid,
                name: v.name,
                status: 'done',
                originFileObj: v.file,
              }))}
              showUploadList={false}
              onChange={handleVideoUpload}
            >
              <p className="ant-upload-drag-icon">
                <CloudUploadOutlined />
              </p>
              <p className="ant-upload-text">点击或拖拽上传视频文件</p>
              <p className="ant-upload-hint">支持 mp4 / mov / mkv</p>
            </Dragger>

            <List
              bordered
              style={{ marginTop: 12 }}
              dataSource={videos}
              locale={{ emptyText: '已选择的视频将显示在这里，可调整顺序与截取秒数' }}
              renderItem={(item, index) => (
                <List.Item
                  actions={[
                    <Space key="trim" size={8} align="center">
                      <span>截取</span>
                      <InputNumber
                        min={0}
                        step={1}
                        value={item.trim ?? 0}
                        onChange={(val) => updateTrim(item.uid, val)}
                        addonAfter="秒"
                      />
                      <Select
                        value={item.trimMode || 'start'}
                        style={{ width: 120 }}
                        options={[
                          { label: '取前N秒', value: 'start' },
                          { label: '取后N秒', value: 'end' },
                        ]}
                        onChange={(val) => updateTrimMode(item.uid, val)}
                      />
                    </Space>,
                    <Button
                      key="up"
                      icon={<ArrowUpOutlined />}
                      size="small"
                      onClick={() => moveVideo(index, -1)}
                      disabled={index === 0}
                    />,
                    <Button
                      key="down"
                      icon={<ArrowDownOutlined />}
                      size="small"
                      onClick={() => moveVideo(index, 1)}
                      disabled={index === videos.length - 1}
                    />,
                    <Button
                      key="del"
                      danger
                      size="small"
                      icon={<DeleteOutlined />}
                      onClick={() => removeVideo(item.uid)}
                    />,
                  ]}
                >
                  <Space direction="vertical" size={0}>
                    <Text strong>{item.name}</Text>
                    <Text type="secondary">顺序 #{index + 1}</Text>
                  </Space>
                </List.Item>
              )}
            />
          </Form.Item>

          <Form.Item label="拼接模式" name="merge_mode">
            <Radio.Group options={MERGE_OPTIONS} optionType="button" buttonStyle="solid" />
          </Form.Item>

          <Form.Item label="启用配音" name="use_voice" valuePropName="checked">
            <Switch />
          </Form.Item>

          <Form.Item label="配音文件（可选）" tooltip="MP3/WAV，若留空且有文本则生成TTS">
            <Upload
              accept="audio/*"
              maxCount={1}
              beforeUpload={() => false}
              fileList={voiceList}
              onChange={({ fileList }) => setVoiceList(fileList)}
            >
              <Button icon={<UploadOutlined />}>选择配音文件</Button>
            </Upload>
          </Form.Item>

          <Form.Item label="配音文本（可选，生成 TTS）" name="voice_text">
            <Input.TextArea
              placeholder="输入文本，留空则不生成TTS"
              autoSize={{ minRows: 3, maxRows: 5 }}
            />
          </Form.Item>

          <Form.Item label="尾帧图片（可选）" tooltip="上传一张图片作为视频结尾停留帧">
            <Upload
              accept="image/*"
              maxCount={1}
              beforeUpload={() => false}
              fileList={tailImage}
              onChange={({ fileList }) => setTailImage(fileList)}
            >
              <Button icon={<UploadOutlined />}>选择尾帧图片</Button>
            </Upload>
          </Form.Item>

          <Form.Item label="尾帧时长（秒）" name="tail_duration" tooltip="仅上传尾帧图片时生效">
            <InputNumber min={0} step={0.5} />
          </Form.Item>

          <Form.Item label="配音混合模式" name="voice_mix_mode">
            <Radio.Group options={VOICE_MIX_OPTIONS} optionType="button" buttonStyle="solid" />
          </Form.Item>

          <Form.Item label="TTS 声音" name="tts_voice">
            <Select options={TTS_OPTIONS} style={{ width: 160 }} />
          </Form.Item>

          <Form.Item label="输出格式" name="output_format">
            <Select options={OUTPUT_FORMATS} style={{ width: 160 }} />
          </Form.Item>

          <Form.Item label="输出文件名（不含后缀，可自动补全）" name="output_name">
            <Input placeholder="例如 merged_output" />
          </Form.Item>

          <Form.Item>
            <Space wrap>
              <Button
                type="primary"
                icon={<PlayCircleOutlined />}
                htmlType="submit"
                loading={submitting}
              >
                开始合成
              </Button>
              <Button icon={<ReloadOutlined />} onClick={resetForm}>
                重置
              </Button>
            </Space>
          </Form.Item>
        </Form>
      </Card>

      <Card className="card" title="任务状态" bordered={false}>
        <Space className="status-bar" wrap>
          <Text strong>状态：</Text>
          {statusTag}
          {jobId && <Text type="secondary">Job ID: {jobId}</Text>}
          {outputPath && <Tag color="blue">输出: {outputPath}</Tag>}
          {downloadUrl && (
            <Button type="link" icon={<DownloadOutlined />} href={downloadUrl} target="_blank">
              下载结果
            </Button>
          )}
          {polling && <Spin size="small" />}
        </Space>

        {errorMsg && (
          <Alert
            style={{ marginTop: 12 }}
            type="error"
            message="任务失败"
            description={errorMsg}
            showIcon
          />
        )}

        <Divider />
        <Paragraph type="secondary" style={{ marginBottom: 0 }}>
          合成完成后，状态会显示为“完成”，点击“下载结果”即可获取输出文件。
        </Paragraph>
      </Card>

      <div className="footer">
        <Text type="secondary">
          后端接口：FastAPI · 前端：React + Ant Design · 局域网直连
        </Text>
      </div>
    </div>
  );
}
