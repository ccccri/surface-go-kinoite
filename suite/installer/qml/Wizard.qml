import QtQuick
import QtQuick.Controls as QQC2
import QtQuick.Layouts
import org.kde.kirigami as Kirigami

Kirigami.ApplicationWindow {
    id: win
    title: "Surface Go installer"
    width: 900
    height: 640
    minimumWidth: 720
    minimumHeight: 520
    pageStack.globalToolBar.style: Kirigami.ApplicationHeaderStyle.None

    readonly property string stage: bridge.stageName
    readonly property var steps: [
        { id: "welcome", t: "Check", d: "Is this the right device?" },
        { id: "restart-mok", t: "Secure Boot key", d: "Update, create and enrol the key" },
        { id: "install", t: "Install", d: "Build the drivers and services" },
        { id: "verify", t: "Verify", d: "Check that everything works" }
    ]
    function stepIndex() {
        switch (stage) {
        case "welcome": return 0
        case "restart-mok": return 1
        case "install": case "restart-after": return 2
        default: return 3
        }
    }
    function anyFail() { var r = bridge.results; for (var i = 0; i < r.length; i++) if (r[i].state === "FAIL") return true; return false }
    property bool showLog: false
    property string errorText: ""
    property var sysChecks: []
    property bool pwFor: false          // which action the password dialog continues
    property string pwAction: ""

    Component.onCompleted: { sysChecks = bridge.systemChecks(); showMaximizedIfSmall() }
    function showMaximizedIfSmall() {}

    Connections {
        target: bridge
        function onLogLine(t) { logArea.append(t.replace(/\n$/, "")) ; }
        function onFailed(msg) { win.errorText = msg; win.showLog = true }
        function onStageChanged() { win.errorText = "" }
    }

    // ---------------------------------------------------------------- password
    QQC2.Dialog {
        id: pwDialog
        modal: true
        anchors.centerIn: QQC2.Overlay.overlay
        title: "Administrator password"
        standardButtons: QQC2.Dialog.Ok | QQC2.Dialog.Cancel
        width: Kirigami.Units.gridUnit * 24
        onOpened: { pwField.text = ""; pwError.visible = false; pwField.forceActiveFocus() }
        onAccepted: {
            if (bridge.checkPassword(pwField.text)) {
                if (win.pwAction === "prepare") bridge.startPrepare()
                else if (win.pwAction === "install") bridge.startInstall(penBox.checked)
                else if (win.pwAction === "verify") bridge.startVerify()
            } else { pwError.visible = true; pwDialog.open() }
        }
        contentItem: ColumnLayout {
            spacing: Kirigami.Units.smallSpacing
            QQC2.Label { text: "The installer needs your password to change system files. It is used only for this installation and kept in memory."; wrapMode: Text.WordWrap; Layout.fillWidth: true }
            QQC2.TextField { id: pwField; echoMode: TextInput.Password; Layout.fillWidth: true; placeholderText: "Password"; onAccepted: pwDialog.accept() }
            QQC2.Label { id: pwError; visible: false; text: "That password was not accepted."; color: Kirigami.Theme.negativeTextColor }
        }
    }
    function askPassword(action) { pwAction = action; pwDialog.open() }

    pageStack.initialPage: Kirigami.Page {
        padding: 0
        RowLayout {
            anchors.fill: parent
            spacing: 0

            // ------------------------------------------------ steps on the left
            Rectangle {
                Layout.fillHeight: true
                Layout.preferredWidth: Kirigami.Units.gridUnit * 14
                color: Qt.rgba(Kirigami.Theme.textColor.r, Kirigami.Theme.textColor.g, Kirigami.Theme.textColor.b, 0.05)
                ColumnLayout {
                    anchors.fill: parent
                    anchors.margins: Kirigami.Units.largeSpacing
                    spacing: Kirigami.Units.largeSpacing
                    Kirigami.Heading { text: "Surface Go"; level: 2 }
                    Repeater {
                        model: win.steps
                        delegate: RowLayout {
                            readonly property int idx: index
                            readonly property bool done: idx < win.stepIndex() || win.stage === "done"
                            readonly property bool now: idx === win.stepIndex() && win.stage !== "done"
                            Layout.fillWidth: true
                            spacing: Kirigami.Units.smallSpacing
                            Rectangle {
                                Layout.preferredWidth: 28; Layout.preferredHeight: 28; radius: 14
                                color: parent.done ? Kirigami.Theme.positiveTextColor : parent.now ? Kirigami.Theme.highlightColor : "transparent"
                                border.width: 1; border.color: Kirigami.Theme.disabledTextColor
                                QQC2.Label {
                                    anchors.centerIn: parent
                                    text: parent.parent.done ? "✓" : (index + 1)
                                    color: (parent.parent.done || parent.parent.now) ? "white" : Kirigami.Theme.textColor
                                }
                            }
                            ColumnLayout {
                                spacing: 0
                                QQC2.Label { text: modelData.t; font.bold: parent.parent.now }
                                QQC2.Label { text: modelData.d; opacity: 0.6; font.pointSize: Kirigami.Theme.defaultFont.pointSize - 1; wrapMode: Text.WordWrap; Layout.fillWidth: true }
                            }
                        }
                    }
                    Item { Layout.fillHeight: true }
                    QQC2.CheckBox { text: "Show details"; checked: win.showLog; onToggled: win.showLog = checked }
                }
            }

            // ------------------------------------------------ the page
            ColumnLayout {
                Layout.fillWidth: true
                Layout.fillHeight: true
                Layout.margins: Kirigami.Units.gridUnit
                spacing: Kirigami.Units.largeSpacing

                // welcome
                ColumnLayout {
                    visible: win.stage === "welcome" && !bridge.busy
                    Layout.fillWidth: true
                    spacing: Kirigami.Units.largeSpacing
                    Kirigami.Heading { text: "Set up your Surface Go"; level: 1 }
                    QQC2.Label {
                        Layout.fillWidth: true; wrapMode: Text.WordWrap
                        text: "This installs the fixes that Linux is missing on the Surface Go: the rear camera and its autofocus, NFC, the volume buttons, the sound tuning and the Surface Control panel. It takes about 20 to 30 minutes and needs an internet connection. Nothing is added to the system image: no layered packages."
                    }
                    Repeater {
                        model: win.sysChecks
                        delegate: RowLayout {
                            Layout.fillWidth: true
                            spacing: Kirigami.Units.smallSpacing
                            Kirigami.Icon { source: modelData.ok ? "emblem-ok-symbolic" : "dialog-warning-symbolic"; Layout.preferredWidth: 20; Layout.preferredHeight: 20 }
                            QQC2.Label { text: modelData.label + ": " + modelData.detail; wrapMode: Text.WordWrap; Layout.fillWidth: true }
                        }
                    }
                    QQC2.Label {
                        Layout.fillWidth: true; wrapMode: Text.WordWrap; opacity: 0.8
                        text: "Step 1 updates the system, creates a signing key for the drivers and asks the firmware to trust it. After that the tablet restarts once."
                    }
                    QQC2.Button { text: "Start"; highlighted: true; icon.name: "go-next"; onClicked: win.askPassword("prepare") }
                }

                // restart for the key
                ColumnLayout {
                    visible: win.stage === "restart-mok" && !bridge.busy
                    Layout.fillWidth: true
                    spacing: Kirigami.Units.largeSpacing
                    Kirigami.Heading { text: "Restart and trust the key"; level: 1 }
                    QQC2.Label {
                        Layout.fillWidth: true; wrapMode: Text.WordWrap
                        text: "When the tablet restarts, a blue screen (\"Perform MOK management\") appears. You have about 10 seconds to press a key, otherwise it starts normally and you must restart again. The Type Cover must be attached."
                    }
                    Rectangle {
                        Layout.fillWidth: true; radius: 8
                        implicitHeight: mokSteps.implicitHeight + Kirigami.Units.largeSpacing * 2
                        color: Qt.rgba(Kirigami.Theme.textColor.r, Kirigami.Theme.textColor.g, Kirigami.Theme.textColor.b, 0.06)
                        QQC2.Label {
                            id: mokSteps
                            anchors.fill: parent; anchors.margins: Kirigami.Units.largeSpacing
                            wrapMode: Text.WordWrap
                            text: "1.  Enroll MOK\n2.  Continue\n3.  Yes\n4.  Type the password:  " + bridge.mokPassword("") + "\n5.  Reboot\n\nThis screen always uses a US keyboard layout, whatever your system language is."
                        }
                    }
                    QQC2.Label { Layout.fillWidth: true; wrapMode: Text.WordWrap; opacity: 0.8; text: "After the restart this window opens again by itself and continues." }
                    QQC2.Button { text: "Restart now"; highlighted: true; icon.name: "system-reboot"; onClicked: bridge.reboot() }
                }

                // install
                ColumnLayout {
                    visible: win.stage === "install" && !bridge.busy
                    Layout.fillWidth: true
                    spacing: Kirigami.Units.largeSpacing
                    Kirigami.Heading { text: "Install the drivers and services"; level: 1 }
                    QQC2.Label {
                        Layout.fillWidth: true; wrapMode: Text.WordWrap
                        text: "The key is trusted. Now the drivers are built for your kernel and signed, libcamera is rebuilt with the camera fixes, and the services and Surface Control are installed. This is the long part (about 15 to 25 minutes); you can keep using the tablet."
                    }
                    QQC2.CheckBox { id: penBox; text: "Also hide the fake 0% Surface Pen battery (optional, adds a few minutes)" }
                    QQC2.Button { text: "Install"; highlighted: true; icon.name: "run-build-install"; onClicked: win.askPassword("install") }
                }

                // restart after install
                ColumnLayout {
                    visible: win.stage === "restart-after" && !bridge.busy
                    Layout.fillWidth: true
                    spacing: Kirigami.Units.largeSpacing
                    Kirigami.Heading { text: "Installed. One more restart"; level: 1 }
                    QQC2.Label { Layout.fillWidth: true; wrapMode: Text.WordWrap; text: "The new drivers load at the next start. After the restart this window opens again and checks that everything works." }
                    QQC2.Button { text: "Restart now"; highlighted: true; icon.name: "system-reboot"; onClicked: bridge.reboot() }
                }

                // verify
                ColumnLayout {
                    visible: (win.stage === "verify" || win.stage === "done") && !bridge.busy
                    Layout.fillWidth: true
                    Layout.fillHeight: true
                    spacing: Kirigami.Units.largeSpacing
                    Kirigami.Heading { text: win.stage !== "done" ? "Check that everything works" : win.anyFail() ? "Some checks failed" : "Everything works"; level: 1 }
                    QQC2.Label {
                        visible: win.stage === "verify"
                        Layout.fillWidth: true; wrapMode: Text.WordWrap
                        text: "This looks at the drivers, the cameras, NFC and the services. It changes nothing."
                    }
                    QQC2.ScrollView {
                        visible: win.stage === "done"
                        Layout.fillWidth: true; Layout.fillHeight: true
                        ListView {
                            clip: true
                            model: bridge.results
                            delegate: RowLayout {
                                width: ListView.view.width
                                spacing: Kirigami.Units.smallSpacing
                                Kirigami.Icon {
                                    visible: modelData.state !== "head"
                                    source: modelData.state === "ok" ? "emblem-ok-symbolic" : modelData.state === "FAIL" ? "dialog-error-symbolic" : "dialog-information-symbolic"
                                    color: modelData.state === "ok" ? Kirigami.Theme.positiveTextColor : modelData.state === "FAIL" ? Kirigami.Theme.negativeTextColor : Kirigami.Theme.textColor
                                    Layout.preferredWidth: 18; Layout.preferredHeight: 18
                                }
                                QQC2.Label {
                                    text: modelData.text
                                    font.bold: modelData.state === "head"
                                    topPadding: modelData.state === "head" ? Kirigami.Units.largeSpacing : 0
                                    wrapMode: Text.WordWrap; Layout.fillWidth: true
                                }
                            }
                        }
                    }
                    RowLayout {
                        QQC2.Button { visible: win.stage === "verify"; text: "Check now"; highlighted: true; icon.name: "dialog-ok"; onClicked: win.askPassword("verify") }
                        QQC2.Button { visible: win.stage === "done"; text: "Open Surface Control"; highlighted: true; icon.name: "computer-laptop"; onClicked: { bridge.openControl(); bridge.finish() } }
                        QQC2.Button { visible: win.stage === "done"; text: "Close"; onClicked: bridge.finish() }
                    }
                }

                // running
                ColumnLayout {
                    visible: bridge.busy
                    Layout.fillWidth: true
                    spacing: Kirigami.Units.largeSpacing
                    Kirigami.Heading { text: "Working..."; level: 1 }
                    QQC2.Label { text: bridge.step; Layout.fillWidth: true; wrapMode: Text.WordWrap }
                    QQC2.ProgressBar { Layout.fillWidth: true; from: 0; to: 1; value: bridge.progress }
                    QQC2.Label { opacity: 0.7; Layout.fillWidth: true; wrapMode: Text.WordWrap; text: "Do not turn the tablet off. A password window of the system may appear once or twice." }
                }

                // error
                Kirigami.InlineMessage {
                    Layout.fillWidth: true
                    visible: win.errorText.length > 0 && !bridge.busy
                    type: Kirigami.MessageType.Error
                    text: win.errorText
                    actions: Kirigami.Action { text: "Try again"; icon.name: "view-refresh"; onTriggered: { win.errorText = ""; win.askPassword(win.stage === "welcome" ? "prepare" : win.stage === "install" || win.stage === "restart-after" ? "install" : "verify") } }
                }

                Item { Layout.fillHeight: !win.showLog }

                // details
                QQC2.ScrollView {
                    visible: win.showLog
                    Layout.fillWidth: true
                    Layout.fillHeight: true
                    Layout.minimumHeight: Kirigami.Units.gridUnit * 8
                    QQC2.TextArea {
                        id: logArea
                        readOnly: true
                        font.family: "monospace"
                        font.pointSize: Kirigami.Theme.defaultFont.pointSize - 1
                        wrapMode: TextEdit.NoWrap
                        onTextChanged: cursorPosition = length
                    }
                }
            }
        }
    }
}
