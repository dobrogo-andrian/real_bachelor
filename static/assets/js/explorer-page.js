(function () {
                const session = window.CommentLabSession;
                const toggleNameButton = document.getElementById('toggle-page-name-selector');
                const toggleIdButton = document.getElementById('toggle-page-id-selector');
                const nameSelectorPanel = document.getElementById('page-name-selector-panel');
                const idSelectorPanel = document.getElementById('page-id-selector-panel');
                const pageNameSelector = document.getElementById('page-name-selector');
                const pageIdSelector = document.getElementById('page-id-selector');
                const selectionResultTitle = document.getElementById('selection-result-title');
                const selectionResultDescription = document.getElementById('selection-result-description');
                const selectionResultSection = document.getElementById('selection-result-section');
                const analysisRoot = document.getElementById('analysis-root');

                if (!toggleNameButton || !toggleIdButton || !nameSelectorPanel || !idSelectorPanel || !pageNameSelector || !pageIdSelector || !selectionResultTitle || !selectionResultDescription || !selectionResultSection || !analysisRoot) {
                    return;
                }

                function togglePanel(panelToToggle, ownButton, otherPanel, otherButton) {
                    const isHidden = panelToToggle.hasAttribute('hidden');
                    if (isHidden) {
                        panelToToggle.removeAttribute('hidden');
                        otherPanel.setAttribute('hidden', '');
                        ownButton.textContent = 'Hide page list';
                        otherButton.textContent = 'Select page to analyze';
                    } else {
                        panelToToggle.setAttribute('hidden', '');
                        ownButton.textContent = 'Select page to analyze';
                    }
                }

                function escapeHtml(value) {
                    return String(value ?? '')
                        .replace(/&/g, '&amp;')
                        .replace(/</g, '&lt;')
                        .replace(/>/g, '&gt;')
                        .replace(/"/g, '&quot;')
                        .replace(/'/g, '&#39;');
                }

                function getAxisLabelStep(items) {
                    if (items.length > 50) {
                        return 5;
                    }
                    if (items.length > 30) {
                        return 3;
                    }
                    return 1;
                }

                function shouldShowDenseValueLabels(itemCount) {
                    return itemCount <= 24;
                }

                function buildSparseValueLabelIndexSet(values) {
                    const numericValues = (values || []).map(function (value) { return Number(value) || 0; });
                    const count = numericValues.length;
                    if (count <= 24) {
                        return new Set(numericValues.map(function (_value, index) { return index; }));
                    }

                    const maxValue = Math.max(...numericValues, 1);
                    const minDistance = count > 80 ? 5 : (count > 50 ? 4 : 3);
                    const candidates = numericValues
                        .map(function (value, index) {
                            const prev = index > 0 ? numericValues[index - 1] : -Infinity;
                            const next = index < count - 1 ? numericValues[index + 1] : -Infinity;
                            const isLocalPeak = value >= prev && value >= next;
                            const prominence = value / maxValue;
                            return { index: index, value: value, isLocalPeak: isLocalPeak, prominence: prominence };
                        })
                        .filter(function (item) {
                            return item.value > 0 && item.isLocalPeak && item.prominence >= 0.2;
                        })
                        .sort(function (left, right) {
                            if (right.value !== left.value) {
                                return right.value - left.value;
                            }
                            return left.index - right.index;
                        });

                    const chosen = [];
                    candidates.forEach(function (candidate) {
                        const tooClose = chosen.some(function (picked) {
                            return Math.abs(picked - candidate.index) < minDistance;
                        });
                        if (!tooClose) {
                            chosen.push(candidate.index);
                        }
                    });

                    return new Set(chosen);
                }

                function buildTrendPath(values, width, height, padding, maxValue, yOffset, valueScale) {
                    if (!values.length) {
                        return '';
                    }

                    const windowSize = values.length > 20 ? 5 : 3;
                    const smoothed = values.map(function (_value, index) {
                        const start = Math.max(0, index - Math.floor(windowSize / 2));
                        const end = Math.min(values.length, index + Math.floor(windowSize / 2) + 1);
                        const slice = values.slice(start, end);
                        const avg = slice.reduce(function (sum, item) { return sum + item; }, 0) / slice.length;
                        return avg;
                    });

                    const plotWidth = width - padding.left - padding.right;
                    const plotHeight = height - padding.top - padding.bottom;
                    const xStep = values.length > 1 ? plotWidth / (values.length - 1) : plotWidth;

                    return smoothed.map(function (value, index) {
                        const x = padding.left + (index * xStep);
                        const scaledValue = Math.min(Math.max(maxValue, 1), (value || 0) * (valueScale || 1));
                        const baseY = padding.top + plotHeight - (scaledValue / Math.max(maxValue, 1)) * plotHeight;
                        const y = Math.max(padding.top + 6, baseY - (yOffset || 0));
                        return (index === 0 ? 'M' : 'L') + x + ' ' + y;
                    }).join(' ');
                }

                function renderLanguageRows(rows) {
                    if (!rows.length) {
                        return '<tr><td colspan="6">No language rows found.</td></tr>';
                    }

                    return rows.map(function (row) {
                        return `
                            <tr>
                                <td>${escapeHtml(row.language)}</td>
                                <td>${escapeHtml(row.total_comments)}</td>
                                <td>${escapeHtml(row.share_percent)}%</td>
                                <td>${escapeHtml(row.positive)}</td>
                                <td>${escapeHtml(row.neutral)}</td>
                                <td>${escapeHtml(row.negative)}</td>
                            </tr>
                        `;
                    }).join('');
                }

                function renderPostRows(rows) {
                    if (!rows.length) {
                        return '<tr><td colspan="8">No post-level rows found.</td></tr>';
                    }

                    return rows.map(function (row) {
                        const postLabel = row.post_href
                            ? `<a class="analysis-post-link" href="${escapeHtml(row.post_href)}" target="_blank" rel="noopener noreferrer">Post ${escapeHtml(row.post_index)}</a>`
                            : `Post ${escapeHtml(row.post_index)}`;
                        return `
                            <tr>
                                <td>${postLabel}</td>
                                <td>${escapeHtml(row.post_time)}</td>
                                <td>${escapeHtml(row.total_comments)}</td>
                                <td>${escapeHtml(row.positive_share)}%</td>
                                <td>${escapeHtml(row.top_language)}</td>
                                <td>${escapeHtml(row.sentiment_counts.positive)}</td>
                                <td>${escapeHtml(row.sentiment_counts.neutral)}</td>
                                <td>${escapeHtml(row.sentiment_counts.negative)}</td>
                            </tr>
                        `;
                    }).join('');
                }

                function renderSolidarityRows(rows) {
                    if (!rows.length) {
                        return '<tr><td colspan="6">No posts reached the 15% comment-share threshold or there was not enough data to compute solidarity.</td></tr>';
                    }

                    return rows.map(function (row) {
                        const postLabel = row.post_href
                            ? `<a class="analysis-post-link" href="${escapeHtml(row.post_href)}" target="_blank" rel="noopener noreferrer">Post ${escapeHtml(row.post_index)}</a>`
                            : `Post ${escapeHtml(row.post_index)}`;
                        return `
                            <tr>
                                <td>${postLabel}</td>
                                <td>${escapeHtml(row.post_time)}</td>
                                <td>${escapeHtml(row.anchor_sentiment)}</td>
                                <td>${escapeHtml(row.solidarity_score)}%</td>
                                <td>${escapeHtml(row.comment_share)}%</td>
                                <td>${escapeHtml(row.compared_comments)} / ${escapeHtml(row.post_total_comments)}</td>
                            </tr>
                        `;
                    }).join('');
                }

                function renderSampleComments(rows) {
                    if (!rows.length) {
                        return '<p>No comments found for this page.</p>';
                    }

                    return rows.map(function (row) {
                        const postTitle = row.post_href
                            ? `<a class="analysis-post-link" href="${escapeHtml(row.post_href)}" target="_blank" rel="noopener noreferrer">Post ${escapeHtml(row.post_index)}</a>`
                            : `Post ${escapeHtml(row.post_index)}`;
                        return `
                            <article class="analysis-comment-card">
                                <h3>${postTitle}</h3>
                                <p class="analysis-meta">${escapeHtml(row.language)} В· ${escapeHtml(row.sentiment)} В· ${escapeHtml(row.likes)} likes</p>
                                <div class="analysis-comment-body">${escapeHtml(row.comment)}</div>
                            </article>
                        `;
                    }).join('');
                }

                function buildBarChartSvg(items, options) {
                    const width = 620;
                    const height = 260;
                    const padding = { top: 18, right: 18, bottom: 64, left: 42 };
                    const plotWidth = width - padding.left - padding.right;
                    const plotHeight = height - padding.top - padding.bottom;
                    const maxValue = Math.max(...items.map(function (item) { return Number(item.value) || 0; }), 1);
                    const barWidth = plotWidth / Math.max(items.length, 1);
                    const color = options.color || '#5fb3b3';
                    const trendPath = options.showTrend
                        ? buildTrendPath(
                            items.map(function (item) { return Number(item.value) || 0; }),
                            width,
                            height,
                            padding,
                            maxValue,
                            options.trendOffset || 10,
                            options.trendScale || 1
                        )
                        : '';

                    const labelStep = getAxisLabelStep(items);
                    const showValueLabels = shouldShowDenseValueLabels(items.length);
                    const labeledValueIndexes = buildSparseValueLabelIndexSet(items.map(function (item) { return item.value; }));
                    const bars = items.map(function (item, index) {
                        const value = Number(item.value) || 0;
                        const h = (value / maxValue) * plotHeight;
                        const x = padding.left + index * barWidth + barWidth * 0.15;
                        const y = padding.top + plotHeight - h;
                        const w = barWidth * 0.7;
                        const showLabel = index % labelStep === 0;
                        const barContent = `
                            <rect x="${x}" y="${y}" width="${w}" height="${h}" rx="4" fill="${color}"></rect>
                            ${showLabel ? `<text x="${x + w / 2}" y="${padding.top + plotHeight + 18}" text-anchor="middle" fill="rgba(255,255,255,0.72)" font-size="10">${escapeHtml(item.label)}</text>` : ''}
                            ${showValueLabels || labeledValueIndexes.has(index) ? `<text x="${x + w / 2}" y="${y - 6}" text-anchor="middle" fill="rgba(255,255,255,0.88)" font-size="10">${value}</text>` : ''}
                        `;
                        if (item.post_href) {
                            return `
                                <a href="${escapeHtml(item.post_href)}" target="_blank" rel="noopener noreferrer">
                                    <title>Open post ${escapeHtml(item.label)}</title>
                                    ${barContent}
                                </a>
                            `;
                        }
                        return `
                            ${barContent}
                        `;
                    }).join('');

                    return `
                        <svg viewBox="0 0 ${width} ${height}" role="img" aria-label="${escapeHtml(options.title)}">
                            <line x1="${padding.left}" y1="${padding.top + plotHeight}" x2="${width - padding.right}" y2="${padding.top + plotHeight}" stroke="rgba(255,255,255,0.18)"></line>
                            <line x1="${padding.left}" y1="${padding.top}" x2="${padding.left}" y2="${padding.top + plotHeight}" stroke="rgba(255,255,255,0.18)"></line>
                            ${trendPath ? `<path d="${trendPath}" fill="none" stroke="rgba(255,255,255,0.38)" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"></path>` : ''}
                            ${bars}
                        </svg>
                    `;
                }

                function buildStackedBarChartSvg(items, options) {
                    const keys = options.keys;
                    const colors = options.colors;
                    const width = 620;
                    const height = 260;
                    const topPadding = options.showSegmentValues ? 54 : 18;
                    const padding = { top: topPadding, right: 18, bottom: 64, left: 42 };
                    const plotWidth = width - padding.left - padding.right;
                    const plotHeight = height - padding.top - padding.bottom;
                    const maxValue = Math.max(...items.map(function (item) {
                        return keys.reduce(function (sum, key) { return sum + (Number(item[key]) || 0); }, 0);
                    }), 1);
                    const barWidth = plotWidth / Math.max(items.length, 1);
                    const trendPaths = (options.trendSeries || []).map(function (series) {
                        return {
                            color: series.color,
                            path: buildTrendPath(
                                items.map(function (item) { return Number(item[series.key]) || 0; }),
                                width,
                                height,
                                padding,
                                maxValue,
                                options.trendOffset || 10,
                                series.scale != null ? series.scale : (options.trendScale || 1)
                            )
                        };
                    });

                    const labelStep = getAxisLabelStep(items);
                    const showValueLabels = shouldShowDenseValueLabels(items.length);
                    const labeledValueIndexes = buildSparseValueLabelIndexSet(items.map(function (item) {
                        return keys.reduce(function (sum, key) { return sum + (Number(item[key]) || 0); }, 0);
                    }));
                    const bars = items.map(function (item, index) {
                        let runningHeight = 0;
                        const x = padding.left + index * barWidth + barWidth * 0.15;
                        const w = barWidth * 0.7;
                        const total = keys.reduce(function (sum, key) { return sum + (Number(item[key]) || 0); }, 0);
                        const showLabel = index % labelStep === 0;
                        const segments = keys.map(function (key) {
                            const value = Number(item[key]) || 0;
                            const h = (value / maxValue) * plotHeight;
                            const y = padding.top + plotHeight - runningHeight - h;
                            runningHeight += h;
                            return `
                                <rect x="${x}" y="${y}" width="${w}" height="${h}" fill="${colors[key]}"></rect>
                            `;
                        }).join('');
                        const topLabelBaseY = padding.top + plotHeight - runningHeight - 6;
                        const valueLabels = options.showSegmentValues
                            ? keys.map(function (key, keyIndex) {
                                const value = Number(item[key]) || 0;
                                if (!value) {
                                    return '';
                                }
                                return `<text x="${x + w / 2}" y="${Math.max(12, topLabelBaseY - (keyIndex * 12))}" text-anchor="middle" fill="${colors[key]}" font-size="10" font-weight="700">${value}</text>`;
                            }).join('')
                            : '';
                        const stackedContent = `
                            ${segments}
                            ${showLabel ? `<text x="${x + w / 2}" y="${padding.top + plotHeight + 18}" text-anchor="middle" fill="rgba(255,255,255,0.72)" font-size="10">${escapeHtml(item.label)}</text>` : ''}
                            ${valueLabels}
                            ${options.showTotals === false ? '' : (showValueLabels || labeledValueIndexes.has(index) ? `<text x="${x + w / 2}" y="${padding.top + plotHeight - runningHeight - 6}" text-anchor="middle" fill="rgba(255,255,255,0.88)" font-size="10">${total}</text>` : '')}
                        `;
                        if (item.post_href) {
                            return `
                                <a href="${escapeHtml(item.post_href)}" target="_blank" rel="noopener noreferrer">
                                    <title>Open post ${escapeHtml(item.label)}</title>
                                    ${stackedContent}
                                </a>
                            `;
                        }
                        return stackedContent;
                    }).join('');

                    return `
                        <svg viewBox="0 0 ${width} ${height}" role="img" aria-label="${escapeHtml(options.title)}">
                            <line x1="${padding.left}" y1="${padding.top + plotHeight}" x2="${width - padding.right}" y2="${padding.top + plotHeight}" stroke="rgba(255,255,255,0.18)"></line>
                            <line x1="${padding.left}" y1="${padding.top}" x2="${padding.left}" y2="${padding.top + plotHeight}" stroke="rgba(255,255,255,0.18)"></line>
                            ${trendPaths.map(function (trend) {
                                return trend.path
                                    ? `<path d="${trend.path}" fill="none" stroke="${trend.color}" stroke-width="3" stroke-linecap="round" stroke-linejoin="round" opacity="0.95"></path>`
                                    : '';
                            }).join('')}
                            ${bars}
                        </svg>
                    `;
                }

                function buildGroupedBarChartSvg(items, options) {
                    const width = 620;
                    const height = 260;
                    const padding = { top: 18, right: 18, bottom: 64, left: 42 };
                    const plotWidth = width - padding.left - padding.right;
                    const plotHeight = height - padding.top - padding.bottom;
                    const groups = Array.from(new Set(items.map(function (item) { return item.label; })));
                    const sentiments = options.series;
                    const maxValue = Math.max(...items.map(function (item) { return Number(item.value) || 0; }), 1);
                    const groupWidth = plotWidth / Math.max(groups.length, 1);
                    const barWidth = (groupWidth * 0.78) / Math.max(sentiments.length, 1);
                    const tickCount = 4;
                    const yTicks = Array.from({ length: tickCount + 1 }, function (_item, index) {
                        const value = (maxValue / tickCount) * index;
                        const y = padding.top + plotHeight - (value / maxValue) * plotHeight;
                        return {
                            value: Math.round(value * 10) / 10,
                            y: y
                        };
                    });

                    const bars = groups.map(function (group, groupIndex) {
                        const x0 = padding.left + groupIndex * groupWidth + groupWidth * 0.11;
                        const groupItems = items.filter(function (item) { return item.label === group; });
                        const inner = sentiments.map(function (seriesName, seriesIndex) {
                            const match = groupItems.find(function (item) { return item.sentiment === seriesName; });
                            const value = match ? (Number(match.value) || 0) : 0;
                            const h = (value / maxValue) * plotHeight;
                            const x = x0 + seriesIndex * barWidth;
                            const y = padding.top + plotHeight - h;
                            return `<rect x="${x}" y="${y}" width="${barWidth - 2}" height="${h}" rx="3" fill="${options.colors[seriesName]}"></rect>`;
                        }).join('');
                        return `
                            ${inner}
                            <text x="${x0 + (groupWidth * 0.78) / 2}" y="${padding.top + plotHeight + 18}" text-anchor="middle" fill="rgba(255,255,255,0.72)" font-size="10">${escapeHtml(group)}</text>
                        `;
                    }).join('');

                    return `
                        <svg viewBox="0 0 ${width} ${height}" role="img" aria-label="${escapeHtml(options.title)}">
                            ${yTicks.map(function (tick) {
                                return `<line x1="${padding.left}" y1="${tick.y}" x2="${width - padding.right}" y2="${tick.y}" stroke="rgba(255,255,255,0.08)"></line>`;
                            }).join('')}
                            <line x1="${padding.left}" y1="${padding.top + plotHeight}" x2="${width - padding.right}" y2="${padding.top + plotHeight}" stroke="rgba(255,255,255,0.18)"></line>
                            <line x1="${padding.left}" y1="${padding.top}" x2="${padding.left}" y2="${padding.top + plotHeight}" stroke="rgba(255,255,255,0.18)"></line>
                            ${yTicks.map(function (tick) {
                                return `<text x="${padding.left - 8}" y="${tick.y + 4}" text-anchor="end" fill="rgba(255,255,255,0.64)" font-size="10">${tick.value}</text>`;
                            }).join('')}
                            ${bars}
                        </svg>
                    `;
                }

                function buildLineChartSvg(seriesList, options) {
                    const width = 620;
                    const height = 280;
                    const padding = { top: 18, right: 18, bottom: 52, left: 42 };
                    const plotWidth = width - padding.left - padding.right;
                    const plotHeight = height - padding.top - padding.bottom;
                    const axisLabels = Array.from(new Set(seriesList.flatMap(function (series) {
                        return (series.points || []).map(function (point) { return String(point.label || ''); });
                    }))).sort(function (left, right) {
                        const leftNumber = Number(left);
                        const rightNumber = Number(right);
                        const leftIsNumber = Number.isFinite(leftNumber);
                        const rightIsNumber = Number.isFinite(rightNumber);
                        if (leftIsNumber && rightIsNumber) {
                            return leftNumber - rightNumber;
                        }
                        return left.localeCompare(right, undefined, { numeric: true });
                    });
                    const xStep = axisLabels.length > 1 ? plotWidth / (axisLabels.length - 1) : plotWidth;
                    const labelToIndex = new Map(axisLabels.map(function (label, index) { return [label, index]; }));
                    const maxValue = options.maxValue || Math.max(...seriesList.flatMap(function (series) {
                        return series.points.map(function (point) { return Number(point.value) || 0; });
                    }), 1);
                    const tickCount = 4;
                    const yTicks = Array.from({ length: tickCount + 1 }, function (_item, index) {
                        const value = (maxValue / tickCount) * index;
                        const y = padding.top + plotHeight - (value / maxValue) * plotHeight;
                        return {
                            value: Math.round(value * 10) / 10,
                            y: y
                        };
                    });

                    const lines = seriesList.map(function (series) {
                        const points = series.points.map(function (point) {
                            const axisIndex = labelToIndex.get(String(point.label || '')) || 0;
                            const x = padding.left + (axisIndex * xStep);
                            const y = padding.top + plotHeight - ((Number(point.value) || 0) / maxValue) * plotHeight;
                            return { x: x, y: y, label: point.label, value: Number(point.value) || 0 };
                        });
                        const path = points.map(function (point, index) {
                            return (index === 0 ? 'M' : 'L') + point.x + ' ' + point.y;
                        }).join(' ');
                        const dots = points.map(function (point) {
                            return `<circle cx="${point.x}" cy="${point.y}" r="3.5" fill="${series.color}"></circle>`;
                        }).join('');
                        return `<path d="${path}" fill="none" stroke="${series.color}" stroke-width="2.5"></path>${dots}`;
                    }).join('');

                    const labelStep = getAxisLabelStep(axisLabels);
                    const labels = axisLabels.map(function (label, index) {
                        if (index % labelStep !== 0) {
                            return '';
                        }
                        const x = padding.left + (index * xStep);
                        return `<text x="${x}" y="${padding.top + plotHeight + 18}" text-anchor="middle" fill="rgba(255,255,255,0.72)" font-size="10">${escapeHtml(label)}</text>`;
                    }).join('');

                    return `
                        <svg viewBox="0 0 ${width} ${height}" role="img" aria-label="${escapeHtml(options.title)}">
                            ${yTicks.map(function (tick) {
                                return `<line x1="${padding.left}" y1="${tick.y}" x2="${width - padding.right}" y2="${tick.y}" stroke="rgba(255,255,255,0.08)"></line>`;
                            }).join('')}
                            <line x1="${padding.left}" y1="${padding.top + plotHeight}" x2="${width - padding.right}" y2="${padding.top + plotHeight}" stroke="rgba(255,255,255,0.18)"></line>
                            <line x1="${padding.left}" y1="${padding.top}" x2="${padding.left}" y2="${padding.top + plotHeight}" stroke="rgba(255,255,255,0.18)"></line>
                            ${yTicks.map(function (tick) {
                                return `<text x="${padding.left - 8}" y="${tick.y + 4}" text-anchor="end" fill="rgba(255,255,255,0.64)" font-size="10">${options.percent ? tick.value + '%' : tick.value}</text>`;
                            }).join('')}
                            ${lines}
                            ${labels}
                        </svg>
                    `;
                }

                function buildMeanSeries(points, windowSize) {
                    const safeWindowSize = Math.max(1, Number(windowSize) || 1);
                    const halfWindow = Math.floor(safeWindowSize / 2);
                    return (points || []).map(function (point, index, list) {
                        const start = Math.max(0, index - halfWindow);
                        const end = Math.min(list.length, index + halfWindow + 1);
                        const window = list.slice(start, end);
                        const avg = window.reduce(function (sum, item) {
                            return sum + (Number(item.value) || 0);
                        }, 0) / Math.max(window.length, 1);
                        return {
                            label: point.label,
                            value: Math.round(avg * 100) / 100
                        };
                    });
                }

                function renderLegend(items) {
                    return `<div class="analysis-legend">${items.map(function (item) {
                        return `<span><i style="background:${item.color}"></i>${escapeHtml(item.label)}</span>`;
                    }).join('')}</div>`;
                }

                function renderChartGallery(charts) {
                    const sentimentColors = {
                        positive: '#4dbb7c',
                        neutral: '#f2c14e',
                        negative: '#e76f51'
                    };
                    const languageTrendColors = ['#8ecae6', '#ffb703', '#fb8500'];
                    const trendSeries = (charts.positivity_trend_by_language || []).map(function (series, index) {
                        return {
                            name: series.name,
                            color: languageTrendColors[index % languageTrendColors.length],
                            points: series.points || []
                        };
                    });
                    const solidarityTrendSeries = (charts.solidarity_trend_by_language || []).map(function (series, index) {
                        return {
                            name: series.name,
                            color: languageTrendColors[index % languageTrendColors.length],
                            points: series.points || []
                        };
                    });
                    const overallTrend = [{
                        name: 'overall',
                        color: '#90be6d',
                        points: charts.positivity_trend_overall || []
                    }];

                    return `
                        <article class="analysis-chart-card span-two">
                            <h3>Comments by post</h3>
                            ${buildBarChartSvg((charts.comments_by_post || []).map(function (item) {
                                return {
                                    label: String(item.label || '').replace(/^P/, ''),
                                    value: item.value,
                                    post_href: item.post_href
                                };
                            }), { title: 'Comments by post', color: '#6ac3ff', showTrend: true, trendOffset: 16 })}
                            <p class="analysis-chart-note">Matches the old countplot by post id, with a moving-average trend line in the background.</p>
                        </article>
                        <article class="analysis-chart-card">
                            <h3>Comments by language</h3>
                            ${buildBarChartSvg(charts.comments_by_language || [], { title: 'Comments by language', color: '#ff9f68' })}
                            <p class="analysis-chart-note">Volume split across detected languages in the selected page.</p>
                        </article>
                        <article class="analysis-chart-card">
                            <h3>Sentiment by language</h3>
                            ${buildStackedBarChartSvg(charts.sentiment_by_language || [], {
                                title: 'Sentiment by language',
                                keys: ['positive', 'neutral', 'negative'],
                                colors: sentimentColors,
                                showSegmentValues: true,
                                showTotals: false
                            })}
                            ${renderLegend([{ label: 'Positive', color: sentimentColors.positive }, { label: 'Neutral', color: sentimentColors.neutral }, { label: 'Negative', color: sentimentColors.negative }])}
                        </article>
                        <article class="analysis-chart-card span-two">
                            <h3>Sentiment by post</h3>
                            ${buildStackedBarChartSvg((charts.sentiment_by_post || []).map(function (item) {
                                return {
                                    label: String(item.label || '').replace(/^P/, ''),
                                    positive: item.positive,
                                    neutral: item.neutral,
                                    negative: item.negative,
                                    post_href: item.post_href,
                                    positive_share: item.positive_share,
                                    neutral_share: item.neutral_share,
                                    negative_share: item.negative_share
                                };
                            }), {
                                title: 'Sentiment by post',
                                keys: ['positive', 'neutral', 'negative'],
                                colors: sentimentColors,
                                trendSeries: [
                                    { key: 'positive_share', color: '#9be2b0', scale: 4.6 },
                                    { key: 'neutral_share', color: '#ffe08a', scale: 4.6 },
                                    { key: 'negative_share', color: '#ff9c7f', scale: 4.6 }
                                ],
                                trendOffset: 28,
                                trendScale: 4.6
                            })}
                            ${renderLegend([{ label: 'Positive', color: sentimentColors.positive }, { label: 'Neutral', color: sentimentColors.neutral }, { label: 'Negative', color: sentimentColors.negative }])}
                        </article>
                        <article class="analysis-chart-card">
                            <h3>Comment length histogram</h3>
                            ${buildBarChartSvg(charts.comment_length_histogram || [], { title: 'Comment length histogram', color: '#b388eb' })}
                            <p class="analysis-chart-note">Distribution of normalized-comment length in words.</p>
                        </article>
                        <article class="analysis-chart-card">
                            <h3>Average length by sentiment</h3>
                            ${buildBarChartSvg(charts.avg_length_by_sentiment || [], { title: 'Average length by sentiment', color: '#7bd389' })}
                            <p class="analysis-chart-note">Replacement for the old length-vs-sentiment boxplot.</p>
                        </article>
                        <article class="analysis-chart-card">
                            <h3>Average length by language and sentiment</h3>
                            ${buildGroupedBarChartSvg(charts.avg_length_by_language_sentiment || [], { title: 'Average length by language and sentiment', series: ['positive', 'neutral', 'negative'], colors: sentimentColors })}
                            ${renderLegend([{ label: 'Positive', color: sentimentColors.positive }, { label: 'Neutral', color: sentimentColors.neutral }, { label: 'Negative', color: sentimentColors.negative }])}
                            <p class="analysis-chart-note">Y-axis shows average comment length in words.</p>
                        </article>
                        <article class="analysis-chart-card">
                            <h3>Average solidarity by language</h3>
                            ${buildBarChartSvg(charts.solidarity_distribution_by_language || [], { title: 'Average solidarity by language', color: '#f28482' })}
                            <p class="analysis-chart-note">Global solidarity trend across languages, excluding unknown.</p>
                        </article>
                        <article class="analysis-chart-card">
                            <h3>Overall positivity trend</h3>
                            ${buildLineChartSvg([{
                                name: 'overall',
                                color: '#90be6d',
                                points: buildMeanSeries((charts.positivity_trend_overall || []).map(function (point) {
                                    return { label: String(point.label || '').replace(/^P/, ''), value: point.value };
                                }), 3)
                            }], { title: 'Overall positivity trend', maxValue: 100, percent: true })}
                            ${renderLegend([{ label: 'Overall positivity', color: '#90be6d' }])}
                            <p class="analysis-chart-note">Y-axis shows positive comments as a percentage of total comments per post.</p>
                        </article>
                        <article class="analysis-chart-card">
                            <h3>Positivity trend by top languages</h3>
                            ${buildLineChartSvg(trendSeries.map(function (series) {
                                return {
                                    name: series.name,
                                    color: series.color,
                                    points: buildMeanSeries((series.points || []).map(function (point) {
                                        return { label: String(point.label || '').replace(/^P/, ''), value: point.value };
                                    }), 5)
                                };
                            }), { title: 'Positivity trend by language', maxValue: 100, percent: true })}
                            ${renderLegend(trendSeries.map(function (series) { return { label: series.name, color: series.color }; }))}
                            <p class="analysis-chart-note">This chart uses a 3-point mean instead of raw per-post values.</p>
                        </article>
                        <article class="analysis-chart-card">
                            <h3>Overall solidarity trend</h3>
                            ${buildLineChartSvg([{
                                name: 'overall solidarity',
                                color: '#f28482',
                                points: buildMeanSeries((charts.solidarity_trend_overall || []).map(function (point) {
                                    return { label: String(point.label || '').replace(/^P/, ''), value: point.value };
                                }), 3)
                            }], { title: 'Overall solidarity trend', maxValue: 100, percent: true })}
                            ${renderLegend([{ label: 'Overall solidarity', color: '#f28482' }])}
                            <p class="analysis-chart-note">This chart uses a 3-point mean instead of raw per-post values.</p>
                        </article>
                        <article class="analysis-chart-card">
                            <h3>Solidarity trend by top languages</h3>
                            ${buildLineChartSvg(solidarityTrendSeries.map(function (series) {
                                return {
                                    name: series.name,
                                    color: series.color,
                                    points: buildMeanSeries((series.points || []).map(function (point) {
                                        return { label: String(point.label || '').replace(/^P/, ''), value: point.value };
                                    }), 5)
                                };
                            }), { title: 'Solidarity trend by language', maxValue: 100, percent: true })}
                            ${renderLegend(solidarityTrendSeries.map(function (series) { return { label: series.name, color: series.color }; }))}
                            <p class="analysis-chart-note">This chart uses a 3-point mean instead of raw per-post values.</p>
                        </article>
                    `;
                }

                function renderAnalysis(result) {
                    if (!result.summary) {
                        analysisRoot.hidden = true;
                        selectionResultDescription.textContent = 'No rows were found in dbo.EnrichedComments for the selected page.';
                        return;
                    }

                    const summary = result.summary;
                    analysisRoot.hidden = false;
                    analysisRoot.innerHTML = `
                        <div class="analysis-kpis">
                            <article class="analysis-card">
                                <h3>Total comments</h3>
                                <span class="analysis-kpi-value">${escapeHtml(summary.total_comments)}</span>
                                <span class="analysis-meta">Selected from enriched comments</span>
                            </article>
                            <article class="analysis-card">
                                <h3>Distinct posts</h3>
                                <span class="analysis-kpi-value">${escapeHtml(summary.distinct_posts)}</span>
                                <span class="analysis-meta">Grouped by PostTime</span>
                            </article>
                            <article class="analysis-card">
                                <h3>Positive share</h3>
                                <span class="analysis-kpi-value">${escapeHtml(summary.positive_share)}%</span>
                                <span class="analysis-meta">Based on Sentiment</span>
                            </article>
                            <article class="analysis-card">
                                <h3>Avg length</h3>
                                <span class="analysis-kpi-value">${escapeHtml(summary.avg_comment_length)}</span>
                                <span class="analysis-meta">Words in NormalizedComment</span>
                            </article>
                        </div>
                        <div class="analysis-grid-two">
                            <article class="analysis-table-card">
                                <h3>Language and sentiment mix</h3>
                                <table class="analysis-table">
                                    <thead>
                                        <tr>
                                            <th>Language</th>
                                            <th>Comments</th>
                                            <th>Share</th>
                                            <th>Positive</th>
                                            <th>Neutral</th>
                                            <th>Negative</th>
                                        </tr>
                                    </thead>
                                    <tbody>${renderLanguageRows(result.language_breakdown)}</tbody>
                                </table>
                            </article>
                            <article class="analysis-table-card">
                                <h3>Top 5 posts by solidarity</h3>
                                <table class="analysis-table">
                                    <thead>
                                        <tr>
                                            <th>Post</th>
                                            <th>Post time</th>
                                            <th>Anchor</th>
                                            <th>Solidarity</th>
                                            <th>Comment share</th>
                                            <th>Compared</th>
                                        </tr>
                                    </thead>
                                    <tbody>${renderSolidarityRows(result.solidarity_top_posts || [])}</tbody>
                                </table>
                            </article>
                        </div>
                        <article class="analysis-table-card">
                            <h3>Post breakdown</h3>
                            <table class="analysis-table">
                                <thead>
                                    <tr>
                                        <th>Post</th>
                                        <th>Post time</th>
                                        <th>Comments</th>
                                        <th>Positive share</th>
                                        <th>Top language</th>
                                        <th>Positive</th>
                                        <th>Neutral</th>
                                        <th>Negative</th>
                                    </tr>
                                </thead>
                                <tbody id="post-breakdown-body">${renderPostRows((result.post_breakdown || []).slice(0, 5))}</tbody>
                            </table>
                            ${(result.post_breakdown || []).length > 5 ? `
                                <div class="analysis-expand-wrap">
                                    <button id="toggle-post-breakdown" class="button analysis-expand-button" type="button">Show all posts</button>
                                </div>
                            ` : ''}
                        </article>
                        <article class="analysis-table-card">
                            <h3>Representative comments</h3>
                            <div class="analysis-comments">${renderSampleComments(result.sample_comments)}</div>
                        </article>
                        <div class="analysis-chart-gallery">
                            ${renderChartGallery(result.charts || {})}
                        </div>
                    `;
                    selectionResultDescription.textContent =
                        'Loaded analysis for ' + (result.page_name || result.selection_value) +
                        ' from dbo.EnrichedComments. Page ID: ' + (result.page_id || 'unknown') +
                        '. Latest processed time: ' + (summary.latest_processed_time || 'unknown') + '.';
                    selectionResultDescription.classList.remove('is-error');

                    const postBreakdownBody = document.getElementById('post-breakdown-body');
                    const togglePostBreakdownButton = document.getElementById('toggle-post-breakdown');
                    if (postBreakdownBody && togglePostBreakdownButton) {
                        let expanded = false;
                        togglePostBreakdownButton.addEventListener('click', function () {
                            expanded = !expanded;
                            postBreakdownBody.innerHTML = renderPostRows(
                                expanded ? result.post_breakdown : result.post_breakdown.slice(0, 5)
                            );
                            togglePostBreakdownButton.textContent = expanded ? 'Show first 5 posts' : 'Show all posts';
                        });
                    }
                }

                async function applySelection(selectionType, selectedValue, modeLabel) {
                    selectionResultTitle.textContent = 'Analyzing ' + selectedValue + ' page...';
                    selectionResultDescription.textContent = 'Loading analysis from dbo.EnrichedComments for the selected ' + modeLabel + '.';
                    selectionResultDescription.classList.remove('is-error');
                    analysisRoot.hidden = true;
                    analysisRoot.innerHTML = '';
                    nameSelectorPanel.setAttribute('hidden', '');
                    idSelectorPanel.setAttribute('hidden', '');
                    toggleNameButton.textContent = 'Select page to analyze';
                    toggleIdButton.textContent = 'Select page to analyze';
                    selectionResultSection.scrollIntoView({ behavior: 'smooth', block: 'start' });

                    try {
                        const rawResponse = await session.fetchWithCsrf('/page-analysis', {
                            method: 'POST',
                            headers: {
                                'Content-Type': 'application/json',
                                'Accept': 'application/json'
                            },
                            body: JSON.stringify({
                                selection_type: selectionType,
                                selection_value: selectedValue
                            })
                        });

                        const response = await session.ensureAuthenticatedResponse(rawResponse);
                        if (!response) {
                            return;
                        }

                        const responseData = await response.json();
                        if (!response.ok) {
                            throw new Error(responseData.error || 'Failed to load page analysis.');
                        }

                        selectionResultTitle.textContent = 'Analysis for ' + selectedValue;
                        renderAnalysis(responseData.result);
                    } catch (error) {
                        selectionResultTitle.textContent = 'Analysis failed for ' + selectedValue;
                        selectionResultDescription.textContent = error.message;
                        selectionResultDescription.classList.add('is-error');
                    }
                }

                toggleNameButton.addEventListener('click', function () {
                    togglePanel(nameSelectorPanel, toggleNameButton, idSelectorPanel, toggleIdButton);
                });

                toggleIdButton.addEventListener('click', function () {
                    togglePanel(idSelectorPanel, toggleIdButton, nameSelectorPanel, toggleNameButton);
                });

                pageNameSelector.addEventListener('change', function () {
                    const selectedPage = pageNameSelector.value;
                    if (selectedPage) {
                        applySelection('page_name', selectedPage, 'page name');
                    }
                });

                pageIdSelector.addEventListener('change', function () {
                    const selectedPageId = pageIdSelector.value;
                    if (selectedPageId) {
                        applySelection('page_id', selectedPageId, 'page id');
                    }
                });
            }());

