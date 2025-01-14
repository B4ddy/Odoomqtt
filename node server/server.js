const express = require('express');
const cors = require('cors');
const { WebSocketServer } = require('ws');
const http = require('http');
require('dotenv').config({ path: './config.env' });

const app = express();
const server = http.createServer(app);
const wss = new WebSocketServer({ server });

// Heartbeat interval (30 seconds)
const HEARTBEAT_INTERVAL = 30000;


app.use(cors({
    origin: '*',  
    methods: ['POST'],
}));

app.use(express.json());

function heartbeat() {
    this.isAlive = true;
}

// ping clients in periods
setInterval(() => {
    wss.clients.forEach((ws) => {
        if (ws.isAlive === false) {
            console.log('Terminating inactive client');
            return ws.terminate();
        }
        ws.isAlive = false;
        ws.ping();
    });
}, HEARTBEAT_INTERVAL);

// Authenticate WebSocket connections
wss.on('connection', (ws, req) => {
    console.log('New client connected:', new Date().toISOString());

    ws.isAlive = true;
    ws.on('pong', heartbeat);

    // Handle client disconnection
    ws.on('close', () => {
        console.log('Client disconnected:', new Date().toISOString());

    });
});

// Debug endpoint to check connected clients
app.get('/status', (req, res) => {
    const status = {
        totalConnections: wss.clients.size,
    };
    res.json(status);
});

// Endpoint for Odoo to send updates
app.post('/update', (req, res) => {
    console.log('Received update:', req.body);

    const { secret, data } = req.body;

    // Verify secret
    if (secret !== process.env.ODOO_SECRET) {
        console.error('Invalid secret received');
        return res.status(403).json({ error: 'Invalid secret' });
    }


    // Send update to all connected clients
    const message = JSON.stringify({
         type: 'update',
         data: data
    });

        let sentCount = 0;
        wss.clients.forEach((client) => {
            if (client.readyState === 1) { // WebSocket.OPEN
                client.send(message);
                sentCount++;
            }
        });
        console.log(`Update sent to ${sentCount} clients`);

    res.json({
        success: true,
        clientCount: wss.clients.size
    });
});

const PORT = process.env.PORT || 8080;
server.listen(PORT, () => {
    console.log(`WebSocket server running on port ${PORT} at ${new Date().toISOString()}`);
});