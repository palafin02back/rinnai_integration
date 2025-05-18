# Rinnai采暖设备集成

[![hacs_badge](https://img.shields.io/badge/HACS-Custom-orange.svg)](https://github.com/custom-components/hacs)
[![GitHub release](https://img.shields.io/github/release/palafin02back/rinnai_integration.svg)](https://github.com/palafin02back/rinnai_integration/releases)
[![GitHub license](https://img.shields.io/github/license/palafin02back/rinnai_integration.svg)](https://github.com/palafin02back/rinnai_integration/blob/master/LICENSE)

此集成允许你在homeassistant中控制和监控林内(Rinnai)G56系列锅炉采暖设备。

## 功能

- 控制采暖温度
- 控制热水温度
- 切换采暖模式（正常模式、节能模式、户外模式）
- 查看设备状态和部分信息
- 支持开/关操作

## 安装

### 方法一：HACS安装（推荐）

1. 确保已安装[HACS](https://hacs.xyz/)
2. 在HACS中点击"自定义存储库"
3. 添加存储库URL: `https://github.com/palafin02back/rinnai_integration`
4. 类别选择"集成"
5. 点击"添加"
6. 在HACS集成页面中搜索"Rinnai"并安装

### 方法二：手动安装

1. 下载此仓库到本地
2. 将`custom_components/rinnai`文件夹复制到您的HomeAssistant配置目录下的`custom_components`文件夹中
3. 重启HomeAssistant

## 配置

此集成支持通过UI配置：

1. 在HomeAssistant的配置 -> 集成中点击"添加集成"
2. 搜索"Rinnai"
3. 按照向导完成配置

## 支持的设备

- 林内采暖设备（G56系列）
- 其他系列暂不支持

## 故障排除

如果遇到问题，请检查以下几点：

1. 确认设备已正确连接到网络
2. 确认设备可以通过原厂APP控制
3. 查看HomeAssistant日志中是否有相关错误信息

## 贡献

欢迎提交问题和改进建议

## 免责声明

此项目仅作为爱好者项目开发，使用风险自负。

## 许可证

本项目采用MIT许可证 - 详情请参阅[LICENSE](LICENSE)文件。