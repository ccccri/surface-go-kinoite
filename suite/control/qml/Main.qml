import QtQuick
import QtQuick.Window
import QtQuick.Controls as QQC2
import QtQuick.Layouts
import org.kde.kirigami as Kirigami

Kirigami.ApplicationWindow {
    id: root
    title: "Surface Control"
    width: 1180
    height: 780
    Component.onCompleted: if (!startTest) showMaximized()

    // the camera pages need room for a 4:3 preview and the settings: never smaller than this
    minimumWidth: 1000
    minimumHeight: 680
    // no title bar of its own: the page content starts at the top and the sidebar says where you are
    pageStack.globalToolBar.style: Kirigami.ApplicationHeaderStyle.None
    pageStack.columnView.columnResizeMode: Kirigami.ColumnView.SingleColumn

    property string current: startPage.replace("Page.qml", "").toLowerCase()
    // remembered while a page goes full screen (the keyboard test), so that the window comes back exactly as it was
    property var savedGeometry: null
    function enterFullScreen() {
        savedGeometry = { x: x, y: y, w: width, h: height, vis: visibility }
        visibility = Window.FullScreen
    }
    function leaveFullScreen() {
        visibility = Window.Windowed
        if (savedGeometry) {
            width = savedGeometry.w; height = savedGeometry.h
            if (savedGeometry.vis === Window.Maximized) visibility = Window.Maximized
            savedGeometry = null
        }
    }
    function go(name, file) {
        root.pageStack.layers.clear()
        root.current = name
        root.pageStack.replace(Qt.resolvedUrl(file))
    }

    globalDrawer: Kirigami.GlobalDrawer {
        isMenu: false
        collapsible: true
        modal: false
        actions: [
            Kirigami.Action { text: "Patches and modules"; icon.name: "dashboard-show-symbolic"; checked: root.current === "overview"; onTriggered: root.go("overview", "OverviewPage.qml") },
            Kirigami.Action { text: "Updates and repair"; icon.name: "system-software-update-symbolic"; checked: root.current === "updates"; onTriggered: root.go("updates", "UpdatesPage.qml") },
            Kirigami.Action { separator: true },
            Kirigami.Action { text: "Cameras"; icon.name: "camera-photo-symbolic"; checked: root.current === "cameras"; onTriggered: root.go("cameras", "CamerasPage.qml") },
            Kirigami.Action { text: "Keyboard cover"; icon.name: "input-keyboard-symbolic"; checked: root.current === "input"; onTriggered: root.go("input", "InputPage.qml") },
            Kirigami.Action { text: "Audio"; icon.name: "audio-speakers-symbolic"; checked: root.current === "audio"; onTriggered: root.go("audio", "AudioPage.qml") },
            Kirigami.Action { text: "NFC"; icon.name: "tag-symbolic"; checked: root.current === "nfc"; onTriggered: root.go("nfc", "NfcPage.qml") },
            Kirigami.Action { text: "Stylus and touch"; icon.name: "draw-freehand-symbolic"; checked: root.current === "stylus"; onTriggered: root.go("stylus", "StylusPage.qml") },
            Kirigami.Action { text: "Sensors and battery"; icon.name: "battery-050-symbolic"; checked: root.current === "sensors"; onTriggered: root.go("sensors", "SensorsPage.qml") }
        ]
    }

    pageStack.initialPage: Qt.resolvedUrl(startPage)

    Connections {
        target: bridge
        function onMessage(text) { root.showPassiveNotification(text, "long") }
    }
}
