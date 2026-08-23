import Combine
import CoreBluetooth
import Foundation

struct LoadCounterSettings: Codable, Equatable {
    let triggerDistanceCm: Int
    let neutralMarginCm: Int
    let timeoutMs: Int
    let cooldownMs: Int
    let brightnessPercent: Int
    let debugMode: Bool
    let sensorOrder: String
    let baseDistance1Cm: Int?
    let baseDistance2Cm: Int?

    enum CodingKeys: String, CodingKey {
        case triggerDistanceCm = "trigger_distance_cm"
        case neutralMarginCm = "neutral_margin_cm"
        case timeoutMs = "timeout_ms"
        case cooldownMs = "cooldown_ms"
        case brightnessPercent = "brightness_percent"
        case debugMode = "debug_mode"
        case sensorOrder = "sensor_order"
        case baseDistance1Cm = "base_distance_1_cm"
        case baseDistance2Cm = "base_distance_2_cm"
    }
}

struct LoadCounterLearningState: Codable, Equatable {
    let active: Bool
    let eventCount: Int
    let phase: String
    let status: String
    let triggerDistanceCm: Int?
    let neutralMarginCm: Int?
    let timeoutMs: Int?
    let cooldownMs: Int?
    let sensorOrder: String?
    let baseDistance1Cm: Int?
    let baseDistance2Cm: Int?

    enum CodingKeys: String, CodingKey {
        case active
        case eventCount = "event_count"
        case phase
        case status
        case triggerDistanceCm = "trigger_distance_cm"
        case neutralMarginCm = "neutral_margin_cm"
        case timeoutMs = "timeout_ms"
        case cooldownMs = "cooldown_ms"
        case sensorOrder = "sensor_order"
        case baseDistance1Cm = "base_distance_1_cm"
        case baseDistance2Cm = "base_distance_2_cm"
    }
}

struct LoadCounterProgramState: Codable, Equatable {
    let active: Bool
    let status: String
}

struct LoadCounterDeviceState: Codable, Equatable {
    let status: String
    let program: LoadCounterProgramState?
    let counter: Int
    let settings: LoadCounterSettings?
    let learning: LoadCounterLearningState?
    let updatedAt: Double

    enum CodingKeys: String, CodingKey {
        case status
        case program
        case counter
        case settings
        case learning
        case updatedAt = "updated_at"
    }
}

final class BluetoothController: NSObject, ObservableObject {
    private let serviceUUID = CBUUID(string: "8fd2f4f8-a7b2-4b2d-a59f-4b2c64850a95")
    private let commandCharacteristicUUID = CBUUID(string: "8fd2f4f9-a7b2-4b2d-a59f-4b2c64850a95")
    private let statusCharacteristicUUID = CBUUID(string: "8fd2f4fa-a7b2-4b2d-a59f-4b2c64850a95")
    private let historyCharacteristicUUID = CBUUID(string: "8fd2f4fb-a7b2-4b2d-a59f-4b2c64850a95")

    @Published var stateText = "Bluetooth starting"
    @Published var lastMessage = "Ready"
    @Published var isReady = false
    @Published var isScanning = false
    @Published var deviceState: LoadCounterDeviceState?
    @Published var historyEvents: [LoadCounterHistoryEvent] = []
    @Published var isLoadingHistory = false
    @Published var historyProgress = 0.0
    @Published var historyError: String?
    @Published var lastHistorySync: Date?
    @Published var isUsingSampleHistory = false

    private var central: CBCentralManager!
    private var peripheral: CBPeripheral?
    private var commandCharacteristic: CBCharacteristic?
    private var statusCharacteristic: CBCharacteristic?
    private var historyCharacteristic: CBCharacteristic?
    private var pendingHistoryCursor: Int?
    private var shouldReconnect = true
    private var deviceHistoryEvents: [LoadCounterHistoryEvent] = []
    private var deviceHistorySyncDate: Date?

    override init() {
        super.init()
        central = CBCentralManager(delegate: self, queue: .main)
    }

    func scan() {
        shouldReconnect = true
        guard central.state == .poweredOn else {
            stateText = bluetoothStateText(central.state)
            return
        }

        isScanning = true
        isReady = false
        commandCharacteristic = nil
        statusCharacteristic = nil
        historyCharacteristic = nil
        stopHistorySync(error: nil)
        stateText = "Scanning"
        central.scanForPeripherals(
            withServices: [serviceUUID],
            options: [CBCentralManagerScanOptionAllowDuplicatesKey: false]
        )
    }

    func disconnect() {
        shouldReconnect = false
        central.stopScan()
        isScanning = false
        isReady = false
        commandCharacteristic = nil
        statusCharacteristic = nil
        if let peripheral {
            central.cancelPeripheralConnection(peripheral)
        }
        stateText = "Disconnected"
    }

    func refreshState() {
        guard let peripheral, let statusCharacteristic else {
            return
        }
        peripheral.readValue(for: statusCharacteristic)
    }

    var historyAvailable: Bool {
        historyCharacteristic != nil
    }

    func refreshHistory() {
        guard isReady, historyCharacteristic != nil else {
            historyError = "History is unavailable on this device"
            return
        }
        historyEvents = []
        isUsingSampleHistory = false
        historyError = nil
        historyProgress = 0
        isLoadingHistory = true
        requestHistoryPage(cursor: 0)
    }

    func loadSampleHistory() {
        stopHistorySync(error: nil)
        if !isUsingSampleHistory {
            deviceHistoryEvents = historyEvents
            deviceHistorySyncDate = lastHistorySync
        }
        historyEvents = SampleHistoryGenerator.events()
        historyError = nil
        historyProgress = 1
        lastHistorySync = Date()
        isUsingSampleHistory = true
    }

    func exitSampleHistory() {
        guard isUsingSampleHistory else { return }
        stopHistorySync(error: nil)
        isUsingSampleHistory = false
        historyEvents = deviceHistoryEvents
        lastHistorySync = deviceHistorySyncDate
        historyError = nil
        historyProgress = historyEvents.isEmpty ? 0 : 1
        if isReady, historyAvailable {
            refreshHistory()
        }
    }

    private func requestHistoryPage(cursor: Int) {
        guard let peripheral, let characteristic = commandCharacteristic else {
            stopHistorySync(error: "Bluetooth disconnected")
            return
        }
        guard let data = "history:\(cursor)".data(using: .utf8) else {
            stopHistorySync(error: "Could not create history request")
            return
        }
        pendingHistoryCursor = cursor
        peripheral.writeValue(data, for: characteristic, type: .withResponse)
    }

    private func receiveHistoryPage(_ data: Data) {
        do {
            let page = try JSONDecoder().decode(LoadCounterHistoryPage.self, from: data)
            guard page.cursor == pendingHistoryCursor else {
                stopHistorySync(error: "History pages arrived out of order")
                return
            }
            historyEvents.append(contentsOf: page.events)
            historyProgress = page.total == 0 ? 1 : min(1, Double(historyEvents.count) / Double(page.total))
            if page.done {
                lastHistorySync = Date()
                deviceHistoryEvents = historyEvents
                deviceHistorySyncDate = lastHistorySync
                stopHistorySync(error: nil)
            } else if page.nextCursor > page.cursor {
                requestHistoryPage(cursor: page.nextCursor)
            } else {
                stopHistorySync(error: "History transfer stopped unexpectedly")
            }
        } catch {
            stopHistorySync(error: "Could not read history data")
        }
    }

    private func stopHistorySync(error: String?) {
        isLoadingHistory = false
        pendingHistoryCursor = nil
        if let error {
            historyError = error
        }
    }

    func send(_ command: String, feedback: String? = nil) {
        if isLoadingHistory {
            stopHistorySync(error: "History sync was interrupted")
        }
        guard let peripheral, let characteristic = commandCharacteristic else {
            lastMessage = "Not connected"
            return
        }
        guard let data = command.data(using: .utf8) else {
            lastMessage = "Invalid command"
            return
        }

        let type: CBCharacteristicWriteType = characteristic.properties.contains(.write)
            ? .withResponse
            : .withoutResponse
        peripheral.writeValue(data, for: characteristic, type: type)
        lastMessage = feedback ?? sentDescription(for: command)

        if type == .withoutResponse {
            DispatchQueue.main.asyncAfter(deadline: .now() + 0.35) { [weak self] in
                self?.refreshState()
            }
        }
    }

    private func sentDescription(for command: String) -> String {
        if command.starts(with: "brightness:") {
            return "Brightness \(command.split(separator: ":").last ?? "")%"
        }
        if command.starts(with: "trigger_distance_cm:") {
            return "Trigger distance \(command.split(separator: ":").last ?? "") cm"
        }
        if command.starts(with: "neutral_margin_cm:") {
            return "Neutral margin \(command.split(separator: ":").last ?? "") cm"
        }
        if command.starts(with: "timeout_ms:") {
            return "Timeout updated"
        }
        if command.starts(with: "cooldown_ms:") {
            return "Cooldown updated"
        }
        if command.starts(with: "counter:") {
            return "Count updated"
        }
        if command.starts(with: "history:") {
            return "History syncing"
        }

        switch command {
        case "loadcounter_start":
            return "Load Counter on"
        case "loadcounter_stop":
            return "Load Counter off"
        case "menu_open":
            return "Opening matrix menu"
        case "menu_cancel":
            return "Closing matrix menu"
        case "learn_start":
            return "Learning started"
        case "learn_calibrate":
            return "Calibrating"
        case "learn_count":
            return "Observing event"
        case "learn_end", "learn_stop":
            return "Learning saved"
        case "learn_cancel":
            return "Learning cancelled"
        case "enter":
            return "Opening matrix menu"
        case "count_reset":
            return "Count reset"
        case "sensor_order_toggle":
            return "Sensor order switched"
        case "calibrate":
            return "Calibrating"
        case "play_animation":
            return "Playing animation"
        case "reset_defaults":
            return "Defaults restored"
        default:
            return "Sent"
        }
    }

    private func userFacingStatus(_ status: String) -> String? {
        let trimmedStatus = status.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !trimmedStatus.isEmpty, trimmedStatus != "ready" else {
            return nil
        }

        if trimmedStatus.starts(with: "ok:") {
            let command = trimmedStatus
                .dropFirst(3)
                .trimmingCharacters(in: .whitespacesAndNewlines)
            return sentDescription(for: command)
        }

        if trimmedStatus.starts(with: "error:") {
            let message = trimmedStatus
                .dropFirst(6)
                .trimmingCharacters(in: .whitespacesAndNewlines)
            return "Error: \(displayText(for: message))"
        }

        return displayText(for: trimmedStatus)
    }

    private func displayText(for rawText: String) -> String {
        rawText.replacingOccurrences(of: "_", with: " ")
    }

    private func bluetoothStateText(_ state: CBManagerState) -> String {
        switch state {
        case .poweredOn:
            return "Bluetooth on"
        case .poweredOff:
            return "Bluetooth off"
        case .unauthorized:
            return "Bluetooth permission needed"
        case .unsupported:
            return "Bluetooth unsupported"
        case .resetting:
            return "Bluetooth resetting"
        case .unknown:
            fallthrough
        @unknown default:
            return "Bluetooth unavailable"
        }
    }

    private func updateDeviceState(from data: Data) {
        do {
            let state = try JSONDecoder().decode(LoadCounterDeviceState.self, from: data)
            deviceState = state
            if let status = userFacingStatus(state.status) {
                lastMessage = status
            }
        } catch {
            if let text = String(data: data, encoding: .utf8), !text.isEmpty {
                lastMessage = userFacingStatus(text) ?? displayText(for: text)
            }
        }
    }
}

extension BluetoothController: CBCentralManagerDelegate {
    func centralManagerDidUpdateState(_ central: CBCentralManager) {
        stateText = bluetoothStateText(central.state)
        if central.state == .poweredOn {
            scan()
        }
    }

    func centralManager(
        _ central: CBCentralManager,
        didDiscover peripheral: CBPeripheral,
        advertisementData: [String: Any],
        rssi RSSI: NSNumber
    ) {
        self.peripheral = peripheral
        peripheral.delegate = self
        central.stopScan()
        isScanning = false
        stateText = "Connecting"
        central.connect(peripheral)
    }

    func centralManager(_ central: CBCentralManager, didConnect peripheral: CBPeripheral) {
        stateText = "Discovering controls"
        peripheral.discoverServices([serviceUUID])
    }

    func centralManager(_ central: CBCentralManager, didFailToConnect peripheral: CBPeripheral, error: Error?) {
        stateText = error?.localizedDescription ?? "Connection failed"
        isReady = false
        commandCharacteristic = nil
        statusCharacteristic = nil
        historyCharacteristic = nil
        stopHistorySync(error: nil)
        if shouldReconnect {
            scan()
        }
    }

    func centralManager(_ central: CBCentralManager, didDisconnectPeripheral peripheral: CBPeripheral, error: Error?) {
        isReady = false
        commandCharacteristic = nil
        statusCharacteristic = nil
        historyCharacteristic = nil
        stopHistorySync(error: "Connection lost")
        stateText = error == nil ? "Disconnected" : "Connection lost"
        if shouldReconnect {
            scan()
        }
    }
}

extension BluetoothController: CBPeripheralDelegate {
    func peripheral(_ peripheral: CBPeripheral, didDiscoverServices error: Error?) {
        if let error {
            stateText = error.localizedDescription
            return
        }

        for service in peripheral.services ?? [] where service.uuid == serviceUUID {
            peripheral.discoverCharacteristics(
                [commandCharacteristicUUID, statusCharacteristicUUID, historyCharacteristicUUID],
                for: service
            )
        }
    }

    func peripheral(_ peripheral: CBPeripheral, didDiscoverCharacteristicsFor service: CBService, error: Error?) {
        if let error {
            stateText = error.localizedDescription
            return
        }

        for characteristic in service.characteristics ?? [] {
            if characteristic.uuid == commandCharacteristicUUID {
                commandCharacteristic = characteristic
            } else if characteristic.uuid == statusCharacteristicUUID {
                statusCharacteristic = characteristic
            } else if characteristic.uuid == historyCharacteristicUUID {
                historyCharacteristic = characteristic
            }
        }

        if commandCharacteristic != nil {
            isReady = true
            stateText = "Connected"
            lastMessage = "Ready"
        } else {
            stateText = "Control characteristic missing"
        }

        refreshState()
        for delay in [0.4, 1.2, 2.0] {
            DispatchQueue.main.asyncAfter(deadline: .now() + delay) { [weak self] in
                self?.refreshState()
            }
        }
    }

    func peripheral(_ peripheral: CBPeripheral, didWriteValueFor characteristic: CBCharacteristic, error: Error?) {
        if let error {
            if pendingHistoryCursor != nil {
                stopHistorySync(error: error.localizedDescription)
            } else {
                lastMessage = error.localizedDescription
            }
            return
        }

        if pendingHistoryCursor != nil, let historyCharacteristic {
            peripheral.readValue(for: historyCharacteristic)
            return
        }

        DispatchQueue.main.asyncAfter(deadline: .now() + 0.2) { [weak self] in
            self?.refreshState()
        }
    }

    func peripheral(_ peripheral: CBPeripheral, didUpdateValueFor characteristic: CBCharacteristic, error: Error?) {
        if let error {
            lastMessage = error.localizedDescription
            return
        }
        guard let data = characteristic.value else {
            return
        }
        if characteristic.uuid == statusCharacteristicUUID {
            updateDeviceState(from: data)
        } else if characteristic.uuid == historyCharacteristicUUID {
            receiveHistoryPage(data)
        }
    }
}
