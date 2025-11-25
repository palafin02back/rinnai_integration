# 林内 (Rinnai) Home Assistant 集成

[![hacs_badge](https://img.shields.io/badge/HACS-Custom-orange.svg)](https://github.com/custom-components/hacs)
[![GitHub release](https://img.shields.io/github/release/palafin02back/rinnai_integration.svg)](https://github.com/palafin02back/rinnai_integration/releases)
[![GitHub license](https://img.shields.io/github/license/palafin02back/rinnai_integration.svg)](https://github.com/palafin02back/rinnai_integration/blob/master/LICENSE)

适用于 Home Assistant 的林内 (Rinnai) 采暖炉/热水器自定义集成组件。
---

## ⚠️ 重要风险警示

**使用本集成存在被官方服务器封号的风险**。一旦被封号，可能导致在原厂 APP 内设备会一直显示离线，无法正常远程控制设备。  
**请在充分知晓风险、自愿承担责任的前提下使用本插件。严格不建议在主账号下使用。开发者及本开源项目对由此带来的损失不承担任何责任。**

---
## 功能特性

- **采暖控制**: 控制采暖温度、模式（普通、节能、户外、快速）以及开关状态。
- **热水器控制**: 设置生活热水温度。
- **传感器**: 监控燃烧状态、燃气用量、出水/采暖温度以及各种运行时间和点火次数统计。
- **预约管理**:
  - 查看和设置采暖预约计划。
  - 切换预约模式（标准型、上班族、节能型、自定义1、自定义2）。
  - 自定义“自定义模式”的预约时间段。
- **能耗监测**: 追踪燃气用量和运行时间。

## 安装

### HACS (推荐)

1. 打开 Home Assistant 中的 [HACS](https://hacs.xyz/)。
2. 进入 "Integrations" (集成) > "Custom repositories" (自定义存储库)。
3. 添加本仓库地址 `https://github.com/palafin02back/rinnai_integration`，并选择 "Integration" (集成) 类别。
4. 搜索 "Rinnai" 并安装。
5. 重启 Home Assistant。

### 手动安装

1. 将 `custom_components/rinnai` 目录复制到您的 Home Assistant `config/custom_components/` 目录下。
2. 重启 Home Assistant。

## 配置

1. 进入 **配置** > **设备与服务**。
2. 点击 **添加集成**。
3. 搜索 **Rinnai**。
4. 输入林内智家app的用户名和密码。

## 使用说明

### 实体介绍

- **Climate (`climate.rinnai_heating`)**: 地暖/采暖的主要控制器。
  - **模式**:
    - `普通模式` (Normal Heating)
    - `节能模式` (Heating Energy Saving)
    - `户外模式` (Heating Outdoor)
    - `快速采暖` (Fast Heating)
- **Water Heater (`water_heater.rinnai_water_heater`)**: 控制生活热水温度。
- **Select (`select.reservation_mode`)**: 选择当前的采暖预约模式。
- **Switch (`switch.heating_reservation`)**: 开启/关闭采暖预约功能。
- **Sensors**:
  - `sensor.gas_usage`: 当前燃气用量。
  - `sensor.burning_state`: 当前锅炉状态（待机、热水加热、燃烧中等）。
  - 以及各种用于统计运行时间和点火次数的诊断传感器。(由于换算规则不清楚，当前展示基于本人机器使用情况推断，欢迎勘误)

### 预约自定义

要自定义 "自定义1" 或 "自定义2" 模式的计划：
1. 在 `select.reservation_mode` 中选择相应的模式。
2. 使用 `text` 实体输入预约计划时间，时间区间形式如'00:00-13:00,14:00-23:00,'。

## 故障排除

- **"No configuration found" (未找到配置)**: 请确认您的设备型号是否受支持。目前主要支持 G56 系列。(其他设备待后续计划添加)
- **实体不可用**: 请检查设备在林内 App 中是否在线。本集成依赖于云端 API。
## 贡献与支持

欢迎提交 Issue 或 PR 反馈问题与建议，协助本集成完善。
## 免责声明

本项目为非官方的爱好者开发项目，不受 Rinnai 官方支持或认证，仅限爱好者研究用途。由此带来封号、设备异常、数据丢失等风险由用户个人承担，开发者及维护者不对此承担任何责任。强烈建议慎重使用！
## 许可证

本项目采用 MIT License，详见 [LICENSE](LICENSE)。