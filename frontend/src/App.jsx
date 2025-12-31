import React, { useMemo, useState } from 'react';
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
  FolderOpenOutlined,
  ArrowUpOutlined,
  ArrowDownOutlined,
  DeleteOutlined,
} from '@ant-design/icons';

const { Title, Paragraph, Text } = Typography;
const { Dragger } = Upload;

const MERGE_OPTIONS = [
  { label: 'A: 原始分辨率拼接', value: 'A' },
  { label: 'B: 统一到最大分辨率', value: 'B' },
  { label: 'C: 统一到首个视频分辨率', value: 'C' },
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

const TRIM_MODE_OPTIONS = [
  { label: '取前 N 秒', value: 'start' },
  { label: '取后 N 秒', value: 'end' },
];

// 从 Ant Upload File 对象中提取文件路径（Electron 环境提供 originFileObj.path）
const getPathFromFile = (file) => file?.originFileObj?.path || file?.path || '';

export default function App() {
  const [form] = Form.useForm();
  const [videos, setVideos] = useState([]);
  const [voiceList, setVoiceList] = useState([]);
  const [tailImage, setTailImage] = useState([]);
  const [running, setRunning] = useState(false);
  const [status, setStatus] = useState('');
  const [outputPath, setOutputPath] = useState('');
  const [errorMsg, setErrorMsg] = useState('');
  const [logs, setLogs] = useState('');

  const statusTag = useMemo(() => {
    if (!status) return <Tag>未开始</Tag>;
    const map = {
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

  const handleSelectOutput = async () => {
    const name = form.getFieldValue('output_name') || 'merged_output';
    const ext = form.getFieldValue('output_format') || 'mp4';
    const target = await window.desktopApi?.selectOutputPath?.(name, ext);
    if (target) {
      setOutputPath(target);
    }
  };

  const resetForm = () => {
    form.resetFields();
    setVideos([]);
    setVoiceList([]);
    setTailImage([]);
    setStatus('');
    setOutputPath('');
    setErrorMsg('');
    setLogs('');
  };

  const handleSubmit = async (values) => {
    if (!window.desktopApi?.runMerge) {
      message.error('Electron API 未就绪，请通过桌面端运行。');
      return;
    }
    const inputPaths = videos
      .map((item) => getPathFromFile(item.file))
      .filter((p) => !!p);
    if (!inputPaths.length) {
      message.warning('请至少选择一个本地视频文件。');
      return;
    }
    if (!outputPath) {
      message.warning('请先选择输出文件路径。');
      return;
    }

    setRunning(true);
    setStatus('running');
    setErrorMsg('');
    setLogs('');

    const trims = videos.map((v) => Number(v.trim) || 0);
    const trimModes = videos.map((v) => v.trimMode || 'start');
    const voicePath = getPathFromFile(voiceList[0]);
    const tailImagePath = getPathFromFile(tailImage[0]);
    const tailDuration = Number(values.tail_duration) || 0;

    const payload = {
      inputs: inputPaths,
      outputPath,
      mergeMode: values.merge_mode,
      useVoice: values.use_voice,
      voicePath: voicePath || '',
      voiceTextContent: values.voice_text || '',
      voiceMixMode: values.voice_mix_mode,
      ttsVoice: values.tts_voice,
      outputFormat: values.output_format,
      trims,
      trimModes,
      tailImagePath: tailImagePath || '',
      tailDuration,
    };

    try {
      const res = await window.desktopApi.runMerge(payload);
      setLogs([res.stdout, res.stderr].filter(Boolean).join('\n'));
      if (res.success) {
        setStatus('done');
        message.success('合成完成');
      } else {
        setStatus('error');
        setErrorMsg(res.error || '运行失败');
        message.error('运行失败，请检查日志或路径。');
      }
    } catch (err) {
      console.error(err);
      setStatus('error');
      setErrorMsg(err?.message || '运行失败');
      message.error('运行失败，请查看日志。');
    } finally {
      setRunning(false);
    }
  };

  return (
    <div className="page">
      <div className="hero">
        <Title level={2} style={{ color: '#fff', marginBottom: 4 }}>
          Video Merge Voiceover · Desktop
        </Title>
        <Paragraph style={{ color: '#f0f5ff', marginBottom: 0 }}>
          多视频拼接 + 配音 + TTS，本地 Electron 桌面端，直接调用 Python CLI。
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
            output_name: 'desktop_output',
            tail_duration: 0,
          }}
          onFinish={handleSubmit}
        >
          <Form.Item
            label="输入视频（可多选，支持拖拽排序）"
            required
            tooltip="按列表顺序拼接，可为每段设置截取前/后 N 秒"
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
              <p className="ant-upload-text">点击或拖拽选择本地视频文件</p>
              <p className="ant-upload-hint">支持 mp4 / mov / mkv</p>
            </Dragger>

            <List
              bordered
              style={{ marginTop: 12 }}
              dataSource={videos}
              locale={{ emptyText: '已选择的视频将显示在此，可调整顺序与截取秒数' }}
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
                        options={TRIM_MODE_OPTIONS}
                        onChange={(val) => updateTrimMode(item.uid, val)}
                        optionFilterProp="label"
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

          <Form.Item label="配音文件（可选）" tooltip="MP3/WAV，若留空且有文本则生成 TTS">
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
              placeholder="输入文本，留空则不生成 TTS"
              autoSize={{ minRows: 3, maxRows: 5 }}
            />
          </Form.Item>

          <Form.Item label="尾帧图片（可选）" tooltip="追加一张图片作为视频结尾帧">
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

          <Form.Item label="输出文件名（仅用于默认名称）" name="output_name">
            <Input placeholder="例如 merged_output" />
          </Form.Item>

          <Form.Item label="输出路径">
            <Space wrap>
              <Button icon={<FolderOpenOutlined />} onClick={handleSelectOutput}>
                选择输出文件
              </Button>
              <Text type={outputPath ? 'secondary' : 'danger'}>{outputPath || '未选择'}</Text>
            </Space>
          </Form.Item>

          <Form.Item>
            <Space wrap>
              <Button
                type="primary"
                icon={<PlayCircleOutlined />}
                htmlType="submit"
                loading={running}
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
          {outputPath && <Tag color="blue">输出: {outputPath}</Tag>}
          {running && <Spin size="small" />}
          {!running && status === 'done' && outputPath && (
            <Button type="link" onClick={() => window.desktopApi?.showItemInFolder?.(outputPath)}>
              打开所在位置
            </Button>
          )}
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
        <Paragraph type="secondary" style={{ marginBottom: 4 }}>
          日志输出（stdout / stderr）：
        </Paragraph>
        <pre
          style={{
            background: '#0d1117',
            color: '#e6edf3',
            padding: 12,
            borderRadius: 8,
            minHeight: 120,
            maxHeight: 260,
            overflow: 'auto',
          }}
        >
          {logs || '暂无日志'}
        </pre>
      </Card>

      <div className="footer">
        <Text type="secondary">Electron 桌面端 · 调用本地 Python CLI，所有处理均在本机完成</Text>
      </div>
    </div>
  );
}
