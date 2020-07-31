//todo add crossfilter stuff here... build some filters and sorters for individual and combined dimensions

class DataFilter {

    constructor(config, imageChannels) {
        var that = this;
        //vars and consts
        this.config = config;
        //all image channels
        this.imageChannels = imageChannels;
        //selections
        this.currentSelection = new Set();
        //x,z coords
        this.x = this.config["featureData"][dataSrcIndex]["xCoordinate"];
        this.y = this.config["featureData"][dataSrcIndex]["yCoordinate"];
        this.phenotypes = [];
    }

    async init() {
        try {
            let response = await fetch('/init_database?' + new URLSearchParams({
                datasource: datasource
            }))
            let response_data = await response.json();
            this.phenotypes = await this.getPhenotypes();
            this.phenotypes.push('');

        } catch (e) {
            console.log("Error Initializing Dataset", e);
        }
    }

    async getRow(row) {
        try {
            let response = await fetch('/get_database_row?' + new URLSearchParams({
                row: row,
                datasource: datasource
            }))
            let response_data = await response.json();
            return response_data;
        } catch (e) {
            console.log("Error Getting Row", e);
        }
    }

    async getSampleRow(row) {
        try {
            let response = await fetch('/get_sample_row?' + new URLSearchParams({
                datasource: datasource
            }))
            let response_data = await response.json();
            return response_data;
        } catch (e) {
            console.log("Error Getting Sample Row", e);
        }
    }

    async getColorScheme(phenotypes) {
        const body = {
            hueFilters: [],
            lightnessRange: ["25", "85"],
            startPalette: [[75, 25, 75]],
            weights: {ciede2000: 1, nameDifference: 0, nameUniqueness: 0, pairPreference: 0},
            paletteSize: _.size(phenotypes)
        }
        //Routing this request to get the proper CORS headers
        let response = await fetch('https://cors-anywhere.herokuapp.com/http://vrl.cs.brown.edu/color/makePalette', {
            headers: new Headers(
                {
                    "Content-Type": "application/json",
                    "Accept": "application/json",
                    'Access-Control-Allow-Origin': '*'
                }
            ),
            method: 'POST',
            body: JSON.stringify(body)
        });
        let responseData = await response.json();
        let colorSchemeList = _.get(responseData, 'palette', []);
        return colorSchemeList;
    }

    async getPhenotypes() {
        try {
            let response = await fetch('/get_phenotypes?' + new URLSearchParams({
                datasource: datasource
            }))
            let response_data = await response.json();
            return response_data;
        } catch (e) {
            console.log("Error Getting Phenotypes", e);
        }
    }


    async getNearestCell(point_x, point_y) {
        try {
            let response = await fetch('/get_nearest_cell?' + new URLSearchParams({
                point_x: point_x,
                point_y: point_y,
                datasource: datasource
            }))
            let cell = await response.json();
            return cell;
        } catch (e) {
            console.log("Error Getting Nearest Cell", e);
        }
    }

    async getNeighborhood(maxDistance, selectedCell) {
        try {
            let pointX = selectedCell[this.x];
            let pointY = selectedCell[this.y];
            let cellId = selectedCell.id;
            let response = await fetch('/get_neighborhood?' + new URLSearchParams({
                point_x: pointX,
                point_y: pointY,
                cellId: cellId,
                max_distance: maxDistance,
                datasource: datasource
            }))
            let neighborhood = await response.json();
            return neighborhood;
        } catch (e) {
            console.log("Error Getting Nearest Cell", e);
        }
    }

    getCurrentSelection() {
        return this.currentSelection;
    }

    clearCurrentSelection() {
        this.currentSelection.clear();
    }


    addToCurrentSelection(item, allowDelete, clearPriors) {

        // delete item on second click
        if (allowDelete && this.currentSelection.has(item)) {
            this.currentSelection.delete(item);
            if (clearPriors) {
                this.currentSelection.clear();
            }

            console.log('current selection size:', this.currentSelection.size);
            if (this.currentSelection.size > 0) {
                console.log('id: ', this.currentSelection.values().next().value.id);
            }
            return;
        }

        // clear previous items
        if (clearPriors) {
            this.currentSelection.clear();
        }

        // add new item
        this.currentSelection.add(item);

        console.log('current selection size:', this.currentSelection.size);
        if (this.currentSelection.size > 0) {
            console.log('id: ', this.currentSelection.values().next().value.id);
        }
    }


    addAllToCurrentSelection(items, allowDelete, clearPriors) {
        console.log("update current selection")
        var that = this;
        that.currentSelection = new Set(items);
        console.log("update current selection done")
    }

    isImageFeature(key) {
        if (this.imageChannels.hasOwnProperty(key)
            && key != 'CellId' && key != 'id' && key != 'CellID' && key != 'ID' && key != 'Area') {
            return true;
        }
        return false;
    }

    getShortChannelName(fullname) {
        var shortname = fullname;
        this.config["imageData"].forEach(function (channel) {
            if (channel.fullname == fullname) {
                shortname = channel.name;
            }
        });
        return shortname;
    }

    getFullChannelName(shortname) {
        var fullname = shortname;
        this.config["imageData"].forEach(function (channel) {
            if (channel.name == shortname) {
                fullname = channel.fullname;
            }
        });
        return fullname;
    }

}
