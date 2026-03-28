# Rinnai 协议逆向参考文档

> 来源：`com.bugull.rinnai.furnace` APK v3.8.1 逆向分析
> 用于校对 HA 集成实现（`custom_components/rinnai/`）

---

## 一、HTTP REST API

### 1.1 基础信息

| 项目 | 值 |
|---|---|
| Base URL | `https://iot.rinnai.com.cn/app` |
| Content-Type | `application/json` |
| 固定 AK | `A39C66706B83CCF0C0EE3CB23A39454D` |
| 密码哈希 | MD5(明文密码) 转大写 |

### 1.2 认证流程

**登录（无需 Bearer Token）**

```
GET /V1/login
Params:
  username      = 用户名
  password      = MD5(password).upper()
  accessKey     = A39C66706B83CCF0C0EE3CB23A39454D
  appType       = "2"
  appVersion    = "1.0.0"
  identityLevel = "0"

Response:
{
  "success": true,
  "data": { "token": "<JWT>" }
}
```

Token 有效期约 24 小时（`REFESH_TIME = 86400`）。集成在每次请求前检查，超时则重新登录。

**后续请求（需 Bearer Token）**

```
Authorization: Bearer <token>
```

### 1.3 所有 API 端点

#### 账号管理

| 名称 | 方法 | URL | 主要参数 |
|---|---|---|---|
| login | GET | `/V1/login` | username, password, accessKey, appType, appVersion, identityLevel |
| get_verification_code | GET | `/V1/getVerificationCode` | phone |
| check_verification_code | GET | `/V1/checkVerificationCode` | code, phone |
| register | POST | `/V1/register` | username, password |
| reset_password | POST | `/V1/reset` | username, password |
| user_permission | GET | `/V2/authPermission` | username（查询业主/租客等身份） |
| logout | POST | `/V1/erase` | — |

#### 设备管理

| 名称 | 方法 | URL | 主要参数 | 集成当前使用 |
|---|---|---|---|---|
| device_list | GET | `/V1/device/list` | — | ✅ 初始化时调用 |
| device_state | GET | `/V1/device/processParameter` | deviceId | ✅ 轮询调用 |
| add_device | POST | `/V1/device/save` | name, mac, authCode, province, city, deviceType | ❌ 未实现 |
| unbind_device | POST | `/V1/device/unbind` | deviceId | ❌ 未实现 |
| rename_device | POST | `/V1/device/update` | name, deviceId | ❌ 未实现 |
| share_device | POST | `/V1/device/share` | username, deviceId | ❌ 未实现 |
| cancel_share | POST | `/V1/device/cancelShare` | deviceId, userId | ❌ 未实现 |
| device_share_persons | GET | `/V1/device/sharedPerson` | deviceId | ❌ 未实现 |
| decrypt_qrcode | POST | `/V1/device/decryptQrcode` | qrcode | ❌ 未实现 |
| bindable_device_list | GET | `/V1/device/bindableList` | deviceId | ❌ 未实现 |
| bind_device | POST | `/V1/device/bind` | mac, deviceIds | ❌ 未实现 |
| update_thermostat_room | POST | `/V1/device/updateRoom` | name, deviceId, roomType | ❌ 未实现 |

#### 能耗与故障

| 名称 | 方法 | URL | 主要参数 | 集成当前使用 |
|---|---|---|---|---|
| gas_water_consumption | POST | `/V1/device/gasWaterConsumption` | date, dateType, deviceId, searchType | ❌ 未实现 |
| air_consumption | GET | `/V1/device/airConsumption` | deviceId, type | ❌ 未实现 |
| fault_code_list | GET | `/V2/faultCode/getCodes` | classID | ❌ 未实现 |
| fault_code_version | GET | `/V1/faultCode/version` | — | ❌ 未实现 |

#### 预约计划

| 名称 | 方法 | URL | 主要参数 | 集成当前使用 |
|---|---|---|---|---|
| get_schedule | GET | `/V1/device/schedule/getScheduleInfo` | mac, type（=heat_type） | ✅ 按需调用 |
| save_schedule | POST | `/V1/device/schedule/saveScheduleHour` | byteStr, mac, type | ✅ 按需调用 |

#### 系统/用户

| 名称 | 方法 | URL | 主要参数 |
|---|---|---|---|
| app_version | GET | `/V1/appVersion` | — |
| firmware_version | GET | `/V1/firmware` | mac |
| get_area | GET | `/V1/area` | — |
| product_list | GET | `/V1/product/getList` | — |

#### 消息通知

| 名称 | 方法 | URL | 主要参数 |
|---|---|---|---|
| message_device_list | GET | `/V1/message/device/list` | type |
| message_share_list | GET | `/V1/message/share/list` | — |
| message_system_list | GET | `/V1/message/system/list` | — |
| message_count | GET | `/V1/message/statistic/count` | msgType |

### 1.4 device_list 响应结构

```json
{
  "success": true,
  "data": {
    "list": [
      {
        "id": "<device_id>",
        "mac": "<MAC地址（大写，12位）>",
        "name": "<设备名称>",
        "deviceType": "<16进制设备型号，如 0F06000C>",
        "classID": "<classID，用于 MQTT id 字段>",
        "authCode": "<设备授权码，用于 MQTT code 字段>",
        "online": true/false
      }
    ]
  }
}
```

### 1.5 device_state 响应结构

```json
{
  "success": true,
  "data": {
    "<fieldName>": "<raw hex value>",
    ...
  }
}
```

字段名与 MQTT `inf/` topic 中的 `enl[].id` 一致（见第二部分）。

---

## 二、MQTT 协议

### 2.1 连接信息

| 项目 | 值 |
|---|---|
| Broker | `mqtt.rinnai.com.cn` |
| Port | `8883`（TLS） |
| Username 格式 | `a:rinnai:SR:01:SR:{username}` |
| Password | MD5(明文密码) 转大写（与 HTTP 相同） |
| 重连策略 | 指数退避 `[5, 10, 30, 60, 120]` 秒 |

### 2.2 Topic 结构

所有 topic 格式为：`rinnai/SR/01/SR/{mac}/{type}/`

| 类型 | 完整 Topic | 方向 | 用途 |
|---|---|---|---|
| `inf` | `rinnai/SR/01/SR/{mac}/inf/` | 设备→云→App | 状态推送（温度、运行模式、预约数据） |
| `stg` | `rinnai/SR/01/SR/{mac}/stg/` | 设备→云→App | 能耗推送（gasUsed、燃烧时长等） |
| `set` | `rinnai/SR/01/SR/{mac}/set/` | App→云→设备 | 控制指令下发 |
| `sys` | `rinnai/SR/01/SR/{mac}/sys/` | 双向 | 心跳（JA4）、绑定/解绑通知 |
| `get` | `rinnai/SR/01/SR/{mac}/get/` | App→设备 | 主动查询（热泵等新设备） |
| `res` | `rinnai/SR/01/SR/{mac}/res/` | 设备→App | 对 `get/` 的响应，格式同 `inf/` |

**当前集成订阅：** `inf/`、`stg/`、`sys/`、`res/`（不订阅 `get/`）

### 2.3 消息格式

#### inf/ 状态推送（code = FFFF）

```json
{
  "code": "FFFF",
  "enl": [
    { "id": "hotWaterTempSetting", "data": "28" },
    { "id": "operationMode",       "data": "00" },
    { "id": "burningState",        "data": "30" }
  ]
}
```

#### inf/ 预约推送（code = 03F1）

```json
{
  "code": "03F1",
  "enl": [
    { "id": "heatingReservationMode",  "data": "0101DB446CDB006E4818C680017F80017F" },
    { "id": "hotWaterReservationMode", "data": "..." }
  ]
}
```

预约数据自动同步到 `byteStr` 字段（集成在 `_handle_state_update()` 中处理）。

#### stg/ 能耗推送（ptn = J05）

```json
{
  "ptn": "J05",
  "egy": [
    { "gasUsed": "00XXXXXX" },
    { "supplyTime": "00XXXXXX" },
    { "totalPowerSupplyTime": "00XXXXXX" },
    { "totalHeatingBurningTime": "XXXX" },
    { "totalHotWaterBurningTime": "XXXX" },
    { "heatingBurningTimes": "XXXX" },
    { "hotWaterBurningTimes": "XXXX" }
  ]
}
```

各字段为 hex 字符串，需经过 processor 链转换（见第三部分）。

#### set/ 控制指令（ptn = J00）

```json
{
  "code": "<authCode>",
  "enl": [
    { "id": "<fieldName>", "data": "<hex value>" }
  ],
  "id": "<classID>",
  "ptn": "J00",
  "sum": "1"
}
```

- `code` 取自 `device_list` 中的 `authCode` 字段
- `id` 取自 `device_list` 中的 `classID` 字段
- 每次指令 `sum=1`，`enl` 可包含多个 key-value 对

#### sys/ 心跳（ptn = JA4）

```json
{ "ptn": "JA4", "epoch": 1234567890 }
```

集成仅记录 debug 日志，不做其他处理。

---

## 三、各设备型号详细说明

### 3.1 采暖炉系列（G56 / G55 / G58）

| 项目 | G56 (0F06000C) | G55 (0F060G55) | G58 (0F060016) |
|---|---|---|---|
| heat_type | G56_HEAT_OVEN | G55_HEAT_OVEN | G58_HEAT_OVEN |
| 热水温度范围 | 35–65°C | 35–65°C | 35–65°C |
| 采暖温度范围 | 35–85°C | 35–85°C | 35–85°C |
| 支持预约 | ✅ | ✅ | ✅ |
| 支持能耗 | ✅ | ✅ | ✅ |

#### G56/G55/G58 MQTT 字段映射

**inf/ 字段（code=FFFF）**

| MQTT 字段 | Processor | HA 属性名 | 说明 |
|---|---|---|---|
| `hotWaterTempSetting` | hex_to_int | `hot_water_temp` | 热水设定温度（°C） |
| `heatingTempSettingNM` | hex_to_int | `heating_temp_nm` | 采暖普通模式设定温度（°C） |
| `heatingTempSettingHES` | hex_to_int | `heating_temp_hes` | 采暖节能模式设定温度（°C） |
| `roomTempControl` | hex_to_int | — | 室温控制值 |
| `heatingOutWaterTempControl` | hex_to_int | — | 出水温控值 |
| `operationMode` | — | `operation_mode` | 运行模式（raw hex string） |
| `burningState` | — | `burning_state` | 燃烧状态（见下表） |

**burningState 值映射**

| 值 | 含义 |
|---|---|
| `30` | Standby（待机） |
| `31` | Heating Water（加热中） |
| `32` | Burning（燃烧中） |
| `33` | Error（故障） |

**inf/ 字段（code=03F1）**

| MQTT 字段 | HA 属性名 | 说明 |
|---|---|---|
| `heatingReservationMode` | `reservation_mode` + `byte_str` | 采暖预约模式 hex 字符串（34 字节） |

**stg/ 字段（ptn=J05）**

| MQTT 字段 | Processor | HA 属性名 | 单位 | 说明 |
|---|---|---|---|---|
| `gasUsed` | hex_to_int ÷ 10000 | `gas_usage` | m³ | 累计燃气用量 |
| `supplyTime` | hex_to_int ÷ 24 | `supply_time` | 天 | 累计通电时长（原始单位：小时） |
| `totalPowerSupplyTime` | hex_to_int ÷ 24 | `total_power_supply_time` | 天 | 总通电时间 |
| `totalHeatingBurningTime` | hex_to_int | `total_heating_burning_time` | 小时 | 采暖燃烧时长 |
| `totalHotWaterBurningTime` | hex_to_int | `total_hot_water_burning_time` | 小时 | 热水燃烧时长 |
| `heatingBurningTimes` | hex_to_int | `heating_burning_times` | 次 | 采暖点火次数 |
| `hotWaterBurningTimes` | hex_to_int | `hot_water_burning_times` | 次 | 热水点火次数 |

**气量精度说明：** 设备上报原始值为 `int(实际m³ × 10000)`，如 `0000270F` = 9999 = 0.9999 m³

#### G56 climate 模式与指令

**operationMode 值 → HA 模式**

| operationMode 值 | HA 模式 | 说明 |
|---|---|---|
| `0`, `1`, `2` | standby | 待机/关闭 |
| `3` | normal | 普通采暖 |
| `B`, `4B` | energy_saving | 节能采暖 |
| `13`, `53` | outdoor | 户外模式 |
| `43`, `63` | rapid | 快速采暖 |

**模式切换指令（20 种 transition）**

| 来源 → 目标 | 指令序列 |
|---|---|
| standby → normal | `summerWinter = "31"` |
| standby → energy_saving | `summerWinter = "31"` (delay 2s) → `energySavingMode = "31"` |
| standby → outdoor | `summerWinter = "31"` (delay 2s) → `outdoorMode = "31"` |
| standby → rapid | `summerWinter = "31"` (delay 2s) → `rapidHeating = "31"` |
| normal → standby | `summerWinter = "31"` |
| normal → energy_saving | `energySavingMode = "31"` |
| normal → outdoor | `outdoorMode = "31"` |
| normal → rapid | `rapidHeating = "31"` |
| energy_saving → standby | `summerWinter = "31"` |
| energy_saving → normal | `energySavingMode = "31"` |
| energy_saving → outdoor | `energySavingMode = "31"` (delay 2s) → `outdoorMode = "31"` |
| energy_saving → rapid | `energySavingMode = "31"` (delay 2s) → `rapidHeating = "31"` |
| outdoor → standby | `summerWinter = "31"` |
| outdoor → normal | `outdoorMode = "31"` |
| outdoor → energy_saving | `outdoorMode = "31"` (delay 2s) → `energySavingMode = "31"` |
| outdoor → rapid | `outdoorMode = "31"` (delay 2s) → `rapidHeating = "31"` |
| rapid → standby | `summerWinter = "31"` |
| rapid → normal | `rapidHeating = "31"` |
| rapid → energy_saving | `rapidHeating = "31"` (delay 2s) → `energySavingMode = "31"` |
| rapid → outdoor | `rapidHeating = "31"` (delay 2s) → `outdoorMode = "31"` |

**温度控制指令**

| 模式 | 读取属性 | 写入字段 | 温度范围 |
|---|---|---|---|
| normal | `heating_temp_nm` | `heatingTempSettingNM` | 35–85°C |
| energy_saving | `heating_temp_hes` | `heatingTempSettingHES` | 35–85°C |
| outdoor | 固定 35°C | — | 不可调 |
| rapid | 固定 85°C | — | 不可调 |

采暖温度编码：`hex(temperature).upper().zfill(2)`（hex2 格式，如 50°C → `"32"`）

**active_states（`burning_state` 值对应 climate action=heating）：** `"31"`, `"32"`

#### 预约计划（schedule）格式

hex 字符串，总长 34 字节（68 hex 字符）：

| 字节偏移 | 含义 |
|---|---|
| 0 | status_byte（预约开关状态） |
| 1 | mode_byte（当前激活的预约模式，1–5） |
| 2–... | 5 个模式数据，每模式 3 字节 |

preset 模式 1–3 的默认值：`0101DB446CDB006E4818C680017F80017F` 等（见设备 JSON `reservation_mode_presets`）

---

### 3.2 E 系列热水器（E86/E88/E89/E65/E75/E76/E66/E51）

所有 E 系列共用相同的 MQTT 字段结构，功能略有差异。

#### 温度编码（hex4 格式）

E 系列使用 4 字符 hex 编码（区别于采暖炉的 2 字符）：

```
40°C → hex(40) = "28" → 补零 → "2800"
```

集成实现（`water_heater.py`）：
```python
hex_temperature = hex(temperature)[2:].upper().zfill(2)
if self._temp_format == "hex4":
    hex_temperature = hex_temperature + "00"
```

#### E 系列 MQTT 字段（inf/ code=FFFF）

| MQTT 字段 | Processor | HA 属性名 | 说明 |
|---|---|---|---|
| `hotWaterTempSetting` | hex_to_int | `hot_water_temp` | 热水设定温度（°C） |
| `operationMode` | — | `operation_mode` | 运行模式 |
| `burningState` | — | `burning_state` | 燃烧状态（同采暖炉） |
| `massageMode` | — | `massage_mode` | 按摩水（`"31"`=on, `"30"`=off） |
| `temporaryCycleInsulationSetting` | — | `cycle_insulation` | 循环保温（`"31"`/`"30"`） |
| `cycleReservationSetting1` | — | `cycle_reservation` | 循环预约设置 |
| `faultCode` | — | `fault_code` | 故障码 |
| `errorCode` | — | `error_code` | 错误码 |

**inf/ 字段（code=03F1）**

| MQTT 字段 | HA 属性名 |
|---|---|
| `hotWaterReservationMode` | `reservation_mode` + `byte_str` |

**stg/ 字段（ptn=J05）**

E 系列只上报一个能耗字段（区别于采暖炉的 7 个）：

| MQTT 字段 | Processor | HA 属性名 | 单位 |
|---|---|---|---|
| `gasConsumption` | hex_to_int ÷ 10000 | `gas_usage` | m³ |

注：E 系列用 `gasConsumption`，采暖炉系列用 `gasUsed`（两者不同）。

#### E 系列 operationMode 选项

| 值 | 选项名 | 适用型号 |
|---|---|---|
| `00` | 正常 | 全系列 |
| `01` | 冬季节能 | 全系列 |
| `02` | 自动 | E86/E88/E89 |
| `03` | 浓薄水 | E65/E75 |

#### E 系列型号差异

| 型号 | classID | 热水温度范围 | 特有功能 |
|---|---|---|---|
| E86 (02720E86) | — | 35–65°C | 按摩水、循环保温、预约 |
| E88 (0272000E) | — | 35–65°C | 同 E86 |
| E89 (02720022) | — | 32–65°C | 同 E86 + 浴缸注水 (`bathWaterInjectionSetting`) |
| E65 (02720010) | — | 35–65°C | 按摩水、浓薄水模式 |
| E75 (0272001C) | — | 35–65°C | 同 E65 |
| E76 (02720E76) | — | 35–65°C | 中端，按摩水 |
| E66 (02720E66) | — | 35–65°C | 中端 |
| E51 (0272000D) | — | 35–65°C | 基础款，3 种运行模式 |

E89 特有字段：`bathWaterInjectionSetting`（浴缸注水开关，`"31"`/`"30"`）

---

### 3.3 RTC-626 室内温控器（0F090004）

**适用场景：** 与采暖炉（G56 等）配套使用的室内温控器

**inf/ 字段**

| MQTT 字段 | Processor | HA 属性名 | 说明 |
|---|---|---|---|
| `power` | — | `power` | 温控器开关（`"01"`/`"00"`） |
| `roomTempSetting` | hex_to_int | `room_temp_setting` | 室温设定（5–35°C） |
| `roomTemperature` | hex_to_int | `room_temperature` | 当前室温（只读） |
| `faultCode` | — | `fault_code` | 故障码 |
| `errorCode` | — | `error_code` | 错误码 |

**控制指令**

| 操作 | 字段 | 值 |
|---|---|---|
| 开机 | `power` | `"01"` |
| 关机 | `power` | `"00"` |
| 设定室温 | `roomTempSetting` | hex2 编码（如 20°C → `"14"`） |

---

### 3.4 热泵温控器（0F090011）

**适用场景：** 与空气源热泵主机配套，支持冷暖模式切换

**inf/ 字段**

| MQTT 字段 | Processor | HA 属性名 | 说明 |
|---|---|---|---|
| `roomTempSetting` | hex_to_int | `room_temp_setting` | 室温设定（5–35°C） |
| `roomTemperature` | hex_to_int | `room_temperature` | 当前室温（只读） |
| `hpUnitColdTempSetting` | hex_to_int | `hp_unit_cold_temp` | 制冷温度设定（16–30°C） |
| `hpUnitHotTempSetting` | hex_to_int | `hp_unit_hot_temp` | 制热温度设定（16–30°C） |
| `operationMode` | — | `operation_mode` | 运行模式 |
| `thermalStatus` | — | `thermal_status` | 热泵运行状态 |
| `hpUnitOperationMode` | — | `hp_unit_operation_mode` | 热泵主机模式 |
| `hpUnitPower` | — | `hp_unit_power` | 热泵开关（`"01"`/`"00"`） |
| `hpUnitConnect` | — | `hp_unit_connect` | 热泵主机连接状态 |
| `faultCode` / `errorCode` | — | `fault_code` / `error_code` | 故障/错误码 |

**控制指令**

| 操作 | 字段 | 值 |
|---|---|---|
| 热泵开机 | `hpUnitPower` | `"01"` |
| 热泵关机 | `hpUnitPower` | `"00"` |
| 制热模式 | `hpUnitOperationMode` | `"00"` |
| 制冷模式 | `hpUnitOperationMode` | `"01"` |
| 设定室温 | `roomTempSetting` | hex2 |
| 制冷设定温度 | `hpUnitColdTempSetting` | hex2 |
| 制热设定温度 | `hpUnitHotTempSetting` | hex2 |

**注：** 热泵温控器使用 `get/` + `res/` topic 进行主动查询（集成已订阅 `res/`）。

---

### 3.5 净水软水器（0F070006）

**inf/ 字段**

| MQTT 字段 | Processor | HA 属性名 | 说明 |
|---|---|---|---|
| `workMode` | — | `work_mode` | 工作状态（0=Working, 1=Regenerating, 2=Error, 3=Off） |
| `saltLevel` | — | `salt_level` | 盐量 |
| `waterHardness` | — | `water_hardness` | 水硬度 |
| `regenCount` | — | `regen_count` | 再生次数（累计） |
| `saltAlarm` | — | `salt_alarm` | 盐量低报警（0=Normal, 1=Low Salt） |
| `waterVelocity` | — | `water_velocity` | 出水流量 |
| `faultCode` / `errorCode` | — | `fault_code` / `error_code` | 故障码 |

**控制指令**

| 操作 | 字段 | 值 |
|---|---|---|
| 立即再生 | `forceRegen` | `"01"` |
| 停止再生 | `forceRegen` | `"00"` |

---

## 四、指令编码规则汇总

### 4.1 温度编码

| 格式 | 说明 | 示例（40°C） | 适用设备 |
|---|---|---|---|
| hex2 | `hex(temp)[2:].upper().zfill(2)` | `"28"` | 采暖炉（G56/G55/G58）、温控器 |
| hex4 | hex2 + `"00"` | `"2800"` | E 系列热水器 |

### 4.2 开关类指令

所有布尔型开关统一使用：
- 开启：`"31"` （采暖炉模式切换）或 `"01"` （设备开关）
- 关闭：`"30"` 或 `"00"`

### 4.3 MQTT 指令完整示例

设置 G56 热水温度为 42°C：

```json
{
  "code": "<authCode>",
  "enl": [
    { "id": "hotWaterTempSetting", "data": "2A" }
  ],
  "id": "<classID>",
  "ptn": "J00",
  "sum": "1"
}
```

G56 从 standby 切换到 normal 模式（通过 set/ topic）：

```json
{
  "code": "<authCode>",
  "enl": [
    { "id": "summerWinter", "data": "31" }
  ],
  "id": "<classID>",
  "ptn": "J00",
  "sum": "1"
}
```

---

## 五、集成实现对照

### 5.1 当前实现覆盖情况

| 协议功能 | 集成实现状态 | 相关文件 |
|---|---|---|
| HTTP 登录 + Token 缓存 | ✅ 完整 | `core/client.py: login()` |
| HTTP 设备列表 | ✅ 完整 | `core/client.py: fetch_devices()` |
| HTTP 设备状态（轮询） | ✅ 完整 | `core/client.py: fetch_device_state()` |
| HTTP 预约 get/save | ✅ 完整 | `core/client.py: perform_request()` |
| MQTT TLS 连接 | ✅ 完整 | `core/mqtt_client.py` |
| MQTT inf/ 状态订阅（code=FFFF） | ✅ 完整 | `client.py: _process_device_info()` |
| MQTT inf/ 预约订阅（code=03F1） | ✅ 完整 | `client.py: _process_reservation_info()` |
| MQTT stg/ 能耗订阅（ptn=J05） | ✅ 完整 | `client.py: _process_energy_data()` |
| MQTT sys/ 心跳（ptn=JA4） | ✅ 接收（仅日志） | `client.py` |
| MQTT res/ 响应订阅 | ✅ 完整 | `client.py` |
| MQTT set/ 指令发送 | ✅ 完整 | `client.py: send_command()` |
| Processor 链（hex_to_int/divide） | ✅ 完整 | `core/processor.py` |
| 采暖炉 climate 5 模式切换 | ✅ 完整 | `climate.py` |
| 采暖炉 climate 模式 delay 指令 | ✅ 完整 | `climate.py` |
| E 系列温度 hex4 编码 | ✅ 完整 | `water_heater.py`, `number.py` |
| 能耗数据持久化（HA storage） | ✅ 完整 | `coordinator.py` |
| 乐观状态（10s 锁） | ✅ 完整 | `core/state_manager.py` |

### 5.2 未实现的 HTTP API（集成范围外）

以下 API 已逆向但未在集成中实现（仅 App 功能）：
- 账号注册/重置密码/验证码
- 设备绑定/解绑/分享
- 历史能耗统计（`gas_water_consumption`）
- 故障码查询（`fault_code_list`）
- 固件版本（`firmware_version`）
- 消息通知（`message_*`）

### 5.3 已知数据字段差异（采暖炉 vs E 系列）

| 项目 | 采暖炉（G56/G55/G58） | E 系列热水器 |
|---|---|---|
| 累计气量 MQTT 字段 | `gasUsed` | `gasConsumption` |
| 气量 energy_data_keys | `gasUsed` | `gasConsumption` |
| 通电时长字段 | `supplyTime`（÷24 天） | 无 |
| 预约 MQTT 字段 | `heatingReservationMode` | `hotWaterReservationMode` |
| 温度编码 | hex2 | hex4 |

> ⚠️ 此前版本的 bug：G56/G55/G58 的 `processors` 和 `state_mapping` 错误地使用了 `gasConsumption`/`actualUseTime` 而非正确的 `gasUsed`/`supplyTime`，导致能耗传感器始终为 unknown。已在当前版本修复。
