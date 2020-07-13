/**

 */
//EVENTHANDLER
const eventHandler = new SimpleEventHandler(d3.select('body').node());
const database = flaskVariables.database;


//VIEWS
let seaDragonViewer;
let distViewer;
let dataFilter;
let dataSrcIndex = 0; // dataset id
let idCount = 0;
let k = 3;
let imageChannels = {}; // lookup table between channel id and channel name (for image viewer)

//Disable right clicking on element
document.getElementById("openseadragon").addEventListener('contextmenu', event => event.preventDefault());

function convertNumbers(row) {
    var r = {};
    r['id'] = idCount + '';
    if (config[database]["featureData"]['id'] && config[database]["featureData"]['id'] != "none") {
        r['id'] = '' + parseInt(row[config[database]["featureData"]['id']] - 1);
    }
    for (var k in row) {
        //convert from string to number and denormalize, if needed.
        // if (config[database]["featureData"][dataSrcIndex]["normalization"] == "exp"){
        //     r[k] = Math.exp(+row[k]);
        // }else{
        r[k] = +row[k];
        // }
    }
    r['cluster'] = '-';
    idCount++;
    return r;
}


//LOAD DATA
console.log('loading config');
// Data prevent caching on the config file, as it may have been modified
d3.json(`/static/data/config.json?t=${Date.now()}`).then(function (config) {
    console.log('loading data');
    this.config = config;
    d3.csv(config[database]["featureData"][dataSrcIndex]["src"], convertNumbers).then(function (data) {
        console.log('data loading finished');
        init(config[database], data);
    });
});


// init all views (datatable, seadragon viewer,...)
function init(conf, data) {

    console.log('initialize system');

    config = conf;
    //channel information
    for (var idx = 0; idx < config["imageData"].length; idx = idx + 1) {
        imageChannels[config["imageData"][idx].fullname] = idx;
    }
    //INIT DATA FILTER
    dataFilter = new DataFilter(config, data, imageChannels);
    dataFilter.wrangleData(dataFilter.getData());
    distViewer = new ChannelList(config, dataFilter, eventHandler);
    distViewer.init(dataFilter.getData());


    //IMAGE VIEWER
    seaDragonViewer = new ImageViewer(config, dataFilter, eventHandler);
    seaDragonViewer.init();

}


//feature color map changed in ridge plot
const actionColorTransferChange = (d) => {

    //map to full name
    d.name = dataFilter.getFullChannelName(d.name);

    d3.select('body').style('cursor', 'progress');
    seaDragonViewer.updateChannelColors(d.name, d.color, d.type);
    d3.select('body').style('cursor', 'default');
}
eventHandler.bind(ChannelList.events.COLOR_TRANSFER_CHANGE, actionColorTransferChange);

//feature color map changed in ridge plot
const actionRenderingModeChange = (d) => {
    seaDragonViewer.updateRenderingMode(d);
}
eventHandler.bind(ImageViewer.events.renderingMode, actionRenderingModeChange);


//feature color map changed in ridge plot
const actionChannelsToRenderChange = (d) => {
    d3.select('body').style('cursor', 'progress');

    //map to full name
    d.name = dataFilter.getFullChannelName(d.name);

    //send to image viewer
    seaDragonViewer.updateActiveChannels(d.name, d.selections, d.status);

    d3.select('body').style('cursor', 'default');
}
eventHandler.bind(ChannelList.events.CHANNELS_CHANGE, actionChannelsToRenderChange);

//image region or single cell selection (may needs to be combined with other selection events)
const actionImageClickedMultiSel = (d) => {
    console.log('actionImageClick3edMultSel');
    d3.select('body').style('cursor', 'progress');
    // add newly clicked item to selection

    console.log('add to selection');
    if (!Array.isArray(d.selectedItem)) {
        dataFilter.addToCurrentSelection(d.selectedItem, true, d.clearPriors);
    } else {
        console.log(d.selectedItem.length);
        dataFilter.addAllToCurrentSelection(d.selectedItem);
    }
    distViewer.highlights(Array.from(dataFilter.getCurrentSelection()));
    updateSeaDragonSelection();
    d3.select('body').style('cursor', 'default');
}
eventHandler.bind(ImageViewer.events.imageClickedMultiSel, actionImageClickedMultiSel);

//current fast solution for seadragon updates
function updateSeaDragonSelection() {
    var arr = Array.from(dataFilter.getCurrentSelection())
    var selectionHashMap = new Map(arr.map(i => ['' + (i.id), i]));
    seaDragonViewer.updateSelection(selectionHashMap);
}
