/** @odoo-module **/

import { registry } from '@web/core/registry';
import { FormController } from '@web/views/form/form_controller';
import { useService } from '@web/core/utils/hooks';

class MrpProductionFormController extends FormController {
    setup() {
        super.setup();
        this.webSocketService = useService("mrp_websocket");
        this.notification = useService("notification");
        this.actionService = useService("action");

        /
    }
}

const mrpWebSocketService = {
    start() {
        let socket = new WebSocket('ws://localhost:8080');

        const connect = () => {
            if (socket.readyState === WebSocket.OPEN) return;

            socket.onopen = () => console.log('WebSocket Connected');
            socket.onmessage = (event) => {
                try {
                    const data = JSON.parse(event.data);
                    if (data.type === 'update' && data.data?.name?.startsWith('WH/MO/')) {
                        if (window.location.href.includes(data.data.id)) {
                            // Check if the state is 'progress' (In Progress) before opening the blueprint
                            if (data.data.state === 'progress' && data.data.blueprint_url) {
                                window.open(data.data.blueprint_url, '_blank');
                            }
                            window.location.reload();
                        }
                    }
                } catch (error) {
                    console.error('Error processing message:', error);
                }
            };
            socket.onclose = () => {
                console.log('WebSocket Disconnected');
                setTimeout(connect, 1000); // Reconnect nach 1 sek
            };
            socket.onerror = (error) => { // error handling
                console.error('WebSocket Error:', error);
            };
        };

        connect();
        return { subscribe: () => {} };
    }
};

//controller regist

registry.category("services").add("mrp_websocket", mrpWebSocketService);
registry.category("views").add("mrp_production_form", {
    type: "form",
    Controller: MrpProductionFormController,
});

export default MrpProductionFormController;