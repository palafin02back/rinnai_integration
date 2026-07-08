"""Constants for the Rinnai integration."""

from typing import Final

# Integration domain
DOMAIN: Final = "rinnai"

# Configuration keys
CONF_USERNAME: Final = "username"
CONF_PASSWORD: Final = "password"
CONF_UPDATE_INTERVAL: Final = "update_interval"
CONF_CONNECT_TIMEOUT: Final = "connect_timeout"
CONF_EXPERIMENTAL_SENSORS: Final = "experimental_sensors"

# Attributes and service names
# These are now defined in device configuration JSON files

# Supported platforms
PLATFORMS: Final = frozenset(["sensor", "water_heater", "climate", "switch", "select", "text"])

# Default values
DEFAULT_UPDATE_INTERVAL: Final = 300  # seconds
DEFAULT_CONNECT_TIMEOUT: Final = 30  # seconds

# Rinnai MQTT settings
RINNAI_HOST: Final = "mqtt.rinnai.com.cn"
RINNAI_PORT: Final = 8883

# Device type identifiers
DEVICE_TYPE_WATER_HEATER: Final = "water_heater"

# Entity categories
ENTITY_CATEGORY_DIAGNOSTIC: Final = "diagnostic"
ENTITY_CATEGORY_CONFIG: Final = "config"

HOST: Final = "https://iot.rinnai.com.cn/app"
BASE_URL: Final = HOST

# Rinnai Smart Home app built-in accessKey
AK: Final = "A39C66706B83CCF0C0EE3CB23A39454D"
REFESH_TIME: Final = 86400  # 24 hours

# Centralized API Request Definitions
# Source: Reverse engineered from com.bugull.rinnai.furnace app v3.8.1
# Service interfaces: Account.kt, Device.kt, User.kt, Message.kt
API_DEFINITIONS: Final = {
    # --- Account ---
    "login": {
        "url": "/V1/login",
        "method": "GET"
    },
    # 获取手机验证码
    "get_verification_code": {
        "url": "/V1/getVerificationCode",
        "method": "GET",
        "params": {"phone": "{phone}"}
    },
    # 校验验证码
    "check_verification_code": {
        "url": "/V1/checkVerificationCode",
        "method": "GET",
        "params": {"code": "{code}", "phone": "{phone}"}
    },
    # 注册账号
    "register": {
        "url": "/V1/register",
        "method": "POST",
        "data": {"username": "{username}", "password": "{password}"}
    },
    # 重置密码
    "reset_password": {
        "url": "/V1/reset",
        "method": "POST",
        "data": {"username": "{username}", "password": "{password}"}
    },
    # 查询账号权限（多身份：业主/租客等）
    "user_permission": {
        "url": "/V2/authPermission",
        "method": "GET",
        "params": {"username": "{username}"}
    },
    # 登出（注销 token）
    "logout": {
        "url": "/V1/erase",
        "method": "POST"
    },

    # --- Device ---
    "device_list": {
        "url": "/V1/device/list",
        "method": "GET"
    },
    "device_state": {
        "url": "/V1/device/processParameter",
        "method": "GET"
    },
    # 添加设备（WiFi 配网后绑定）
    "add_device": {
        "url": "/V1/device/save",
        "method": "POST",
        "data": {
            "name": "{name}",
            "mac": "{mac}",
            "authCode": "{auth_code}",
            "province": "{province}",
            "city": "{city}",
            "deviceType": "{device_type}"
        }
    },
    # 解绑/删除设备
    "unbind_device": {
        "url": "/V1/device/unbind",
        "method": "POST",
        "data": {"deviceId": "{device_id}"}
    },
    # 重命名设备
    "rename_device": {
        "url": "/V1/device/update",
        "method": "POST",
        "data": {"name": "{name}", "deviceId": "{device_id}"}
    },
    # 设备分享给其他用户
    "share_device": {
        "url": "/V1/device/share",
        "method": "POST",
        "data": {"username": "{username}", "deviceId": "{device_id}"}
    },
    # 取消设备分享
    "cancel_share": {
        "url": "/V1/device/cancelShare",
        "method": "POST",
        "data": {"deviceId": "{device_id}", "userId": "{user_id}"}
    },
    # 获取设备分享人列表
    "device_share_persons": {
        "url": "/V1/device/sharedPerson",
        "method": "GET",
        "params": {"deviceId": "{device_id}"}
    },
    # 扫码解析设备 MAC
    "decrypt_qrcode": {
        "url": "/V1/device/decryptQrcode",
        "method": "POST",
        "data": {"qrcode": "{qrcode}"}
    },
    # 燃气/用水量历史统计
    "gas_water_consumption": {
        "url": "/V1/device/gasWaterConsumption",
        "method": "POST",
        "data": {
            "date": "{date}",
            "dateType": "{date_type}",
            "deviceId": "{device_id}",
            "searchType": "{search_type}"
        }
    },
    # 空气消耗量（用于净水器等）
    "air_consumption": {
        "url": "/V1/device/airConsumption",
        "method": "GET",
        "params": {"deviceId": "{device_id}", "type": "{type}"}
    },
    # 故障码列表（按设备 classID 查询）
    "fault_code_list": {
        "url": "/V2/faultCode/getCodes",
        "method": "GET",
        "params": {"classID": "{class_id}"}
    },
    # 故障码版本
    "fault_code_version": {
        "url": "/V1/faultCode/version",
        "method": "GET"
    },
    # 可绑定设备列表（用于热泵温控器绑定采暖炉）
    "bindable_device_list": {
        "url": "/V1/device/bindableList",
        "method": "GET",
        "params": {"deviceId": "{device_id}"}
    },
    # 绑定子设备（热泵温控器 ↔ 热泵主机）
    "bind_device": {
        "url": "/V1/device/bind",
        "method": "POST",
        "data": {"mac": "{mac}", "deviceIds": "{device_ids}"}
    },
    # 温控器绑定房间类型（地暖/风盘/散热器）
    "update_thermostat_room": {
        "url": "/V1/device/updateRoom",
        "method": "POST",
        "data": {"name": "{name}", "deviceId": "{device_id}", "roomType": "{room_type}"}
    },

    # --- Schedule ---
    "get_schedule": {
        "url": "/V1/device/schedule/getScheduleInfo",
        "method": "GET",
        "params": {
            "mac": "{mac}",
            "type": "{heat_type}"
        }
    },
    "save_schedule": {
        "url": "/V1/device/schedule/saveScheduleHour",
        "method": "POST",
        "data": {
            "byteStr": "{data}",
            "mac": "{mac}",
            "type": "{heat_type}"
        }
    },

    # --- User ---
    # App 版本检查
    "app_version": {
        "url": "/V1/appVersion",
        "method": "GET"
    },
    # 固件版本查询
    "firmware_version": {
        "url": "/V1/firmware",
        "method": "GET",
        "params": {"mac": "{mac}"}
    },
    # 获取省市区列表
    "get_area": {
        "url": "/V1/area",
        "method": "GET"
    },
    # 获取所有产品类型（classID → 产品名称映射）
    "product_list": {
        "url": "/V1/product/getList",
        "method": "GET"
    },

    # --- Message ---
    # 设备消息列表（故障、维护等）
    "message_device_list": {
        "url": "/V1/message/device/list",
        "method": "GET",
        "params": {"type": "{type}"}
    },
    # 分享消息列表
    "message_share_list": {
        "url": "/V1/message/share/list",
        "method": "GET"
    },
    # 系统消息列表
    "message_system_list": {
        "url": "/V1/message/system/list",
        "method": "GET"
    },
    # 未读消息数量统计
    "message_count": {
        "url": "/V1/message/statistic/count",
        "method": "GET",
        "params": {"msgType": "{msg_type}"}
    },
}

# MQTT Definitions
# Source: Reverse engineered from com.bugull.rinnai.furnace app v3.8.1
# Topic builder: ExtensionKt.getTopic(mac, type) = "rinnai/SR/01/SR/{mac}/{type}/"
MQTT_DEFINITIONS: Final = {
    "topics": {
        # 设备状态推送（burningState, operationMode, 温度等）
        "info": "rinnai/SR/01/SR/{mac}/inf/",
        # 能耗数据推送（gasUsed, 燃烧时长等）
        "energy": "rinnai/SR/01/SR/{mac}/stg/",
        # 下发控制指令
        "set": "rinnai/SR/01/SR/{mac}/set/",
        # 系统事件（设备绑定/解绑通知、在线心跳 JA4）
        "sys": "rinnai/SR/01/SR/{mac}/sys/",
        # 主动查询设备状态（热泵等新设备使用）
        "get": "rinnai/SR/01/SR/{mac}/get/",
        # 设备响应（get 的回包）
        "res": "rinnai/SR/01/SR/{mac}/res/",
    },
    "protocol": {
        "info_code": "FFFF",
        "reservation_code": "03F1",
        "energy_pattern": "J05",
        "command_pattern": "J00",
        "command_sum": "1",
        # sys topic: 设备上线/下线通知，格式 {"ptn":"JA3","online":"1"|"0","timestamp":<ms>}
        "online_pattern": "JA3",
        # sys topic: 周期心跳（未在实测中观察到，暂保留）
        "heartbeat_pattern": "JA4",
    }
}



